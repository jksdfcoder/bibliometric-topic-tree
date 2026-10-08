"""Bounded, read-only pilot for the user-reported relational OpenAlex schema.

Does not infer full lake coverage or restore author identities. One partition only.
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import resource
import time
import pyarrow.parquet as pq
from atlas_data import normalize, digest, records, update_key


def file_info(path):
    stat = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return {'path': str(path), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'sha256': h.hexdigest()}


def pilot(root, partition, output, config, archive_side_tables=False):
    start = time.monotonic()
    root, output = root.resolve(), output.resolve()
    if not partition or Path(partition).name != partition:
        raise ValueError('partition must be one directory name')
    if output == root or root in output.parents:
        raise ValueError('output must be outside the source tree')
    works = sorted((root/'works'/partition).glob('*.parquet'))
    if not works:
        raise ValueError('partition has no works parquet')
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'status':'running', 'adapter':'relational-partition-pilot-v1',
                'partition':partition, 'config':config, 'archive_side_tables':archive_side_tables, 'source_version':f'lake-partition:{partition}',
                'created_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'input_files':[],
                'code_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
                               [Path(__file__), Path(__file__).with_name('atlas_data.py')]},
                'limitations':['single update partition; not full five-year corpus',
                               'no raw author names or affiliations available in reported tables',
                               'same-partition references joined by work ID and updated_date; provenance unverified',
                               'reference row absence is unknown, never factual zero references',
                               'scope is unverified textual candidates; no source-name recall in this pilot']}
    try:
        counts, chosen = Counter(), {}
        for path in works:
            manifest['input_files'].append(file_info(path))
            for raw in records(path, all_columns=True):
                counts['scanned_work_records'] += 1
                normalized, reason = normalize(raw, config, manifest['source_version'])
                if reason:
                    counts[reason] += 1
                # Resolve versions before final scope selection, including rows leaving scope.
                wid = raw['id']
                timestamp = str(raw.get('updated') or raw.get('updated_date') or '')
                signature = digest(raw)
                if wid in chosen:
                    old = chosen[wid]
                    if old['hash'] == signature:
                        continue
                    a, b = update_key(old['timestamp']), update_key(timestamp)
                    if a is None or b is None or a == b:
                        raise ValueError('unresolved duplicate version: ' + str(wid))
                    if a > b:
                        continue
                chosen[wid] = {'timestamp':timestamp, 'hash':signature, 'row':normalized,
                               'date':str(raw.get('updated_date') or ''), 'raw':raw if normalized else None}
        chosen = {k:v for k,v in chosen.items() if v['row'] is not None}
        archive = output/'source_archive'
        archive.mkdir()
        with (archive/'works.jsonl').open('w') as stream:
            for wid in sorted(chosen):
                stream.write(json.dumps({'source_record':chosen[wid]['raw'],
                                         'source_version':manifest['source_version']},
                                        ensure_ascii=False, default=str)+'\n')
        if archive_side_tables:
            archive_tables(root, partition, output, chosen, manifest, counts)
        # Only scan reference side-table files in the explicitly selected partition.
        refs = {k:set() for k in chosen}
        side = sorted((root/'works_referenced_works'/partition).glob('*.parquet'))
        for path in side:
            manifest['input_files'].append(file_info(path))
            p = pq.ParquetFile(path)
            expected = {'id','updated_date','referenced_work_id'}
            if not expected <= set(p.schema_arrow.names):
                raise ValueError('unexpected reference side-table schema')
            for batch in p.iter_batches(batch_size=65536, columns=sorted(expected)):
                # Filter in Arrow before Python conversion: ID condition only; no author IDs.
                import pyarrow as pa
                import pyarrow.compute as pc
                if not chosen:
                    break
                filtered = batch.filter(pc.is_in(batch.column(batch.schema.get_field_index('id')),
                                                 value_set=pa.array(list(chosen), type=pa.int64())))
                for edge in filtered.to_pylist():
                    wid = edge['id']
                    if str(edge['updated_date']) != chosen[wid]['date']:
                        counts['reference_version_mismatch'] += 1
                        continue
                    target = edge['referenced_work_id']
                    if target is None:
                        counts['null_reference_endpoint'] += 1
                        continue
                    refs[wid].add(target)
        with (output/'works.jsonl').open('w') as wf, (output/'references.jsonl').open('w') as rf:
            for wid in sorted(chosen):
                row = chosen[wid]['row']
                row.pop('references', None)
                row.pop('mentions', None)
                row['reference_status'] = 'side_table_present_unverified' if refs[wid] else 'unknown_no_matching_rows'
                row['authorship_status'] = 'raw_mentions_unavailable'
                row['reference_join_method'] = 'same_partition_work_id_updated_date'
                counts['candidates'] += 1
                counts['candidate_year_'+row['publication_date'][:4]] += 1
                counts['candidate_abstract_'+row['abstract_status']] += 1
                counts['candidate_reference_'+row['reference_status']] += 1
                wf.write(json.dumps(row, ensure_ascii=False)+'\n')
                for target in sorted(refs[wid]):
                    rf.write(json.dumps({'citing':row['work_id'], 'cited':f'https://openalex.org/W{target}',
                                         'evidence':'direct_reference', 'source_version':manifest['source_version'],
                                         'source_updated_date':chosen[wid]['date'],
                                         'join_method':'same_partition_work_id_updated_date'})+'\n')
                    counts['reference_edges'] += 1
        for item in manifest['input_files']:
            after = Path(item['path']).stat()
            if (after.st_size,after.st_mtime_ns) != (item['bytes'],item['mtime_ns']):
                raise ValueError('source changed during run')
        manifest.update(status='completed', counts=dict(counts), elapsed_seconds=time.monotonic()-start,
                        peak_rss_native=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        rss_unit='KiB on Linux; bytes on macOS',
                        sample_titles=[chosen[k]['row']['title'] for k in sorted(chosen)[:10]])
    except Exception as exc:
        manifest.update(status='failed', error=str(exc))
        raise
    finally:
        (output/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    return manifest



def archive_tables(root, partition, output, chosen, manifest, counts):
    """Loss-preserving source archive; separate from trusted normalized evidence."""
    import pyarrow as pa
    import pyarrow.compute as pc
    keys = pa.array(list(chosen), type=pa.int64())
    reports = {}
    with (output/'incoming_citations_partial.jsonl').open('w') as incoming:
        for table in sorted(root.iterdir()):
            if not table.is_dir() or not table.name.startswith('works_'):
                continue
            files = sorted((table/partition).glob('*.parquet'))
            if not files:
                reports[table.name] = {'status':'partition_absent', 'rows':0}
                continue
            count = 0
            for path in files:
                manifest['input_files'].append(file_info(path))
                p = pq.ParquetFile(path)
                names = set(p.schema_arrow.names)
                if 'id' not in names:
                    raise ValueError('side table lacks work ID: '+str(path))
                quarantine = 'author_id' in names
                folder = output/('identity_source_quarantine' if quarantine else 'source_archive')
                folder.mkdir(exist_ok=True)
                with (folder/(table.name+'.jsonl')).open('a') as target:
                    for batch in p.iter_batches(batch_size=8192):
                        idx = batch.schema.get_field_index('id')
                        selected = batch.filter(pc.is_in(batch.column(idx),value_set=keys))
                        for row in selected.to_pylist():
                            match = str(row.get('updated_date') or '') == chosen[row['id']]['date']
                            target.write(json.dumps({'source_file':str(path), 'source_record':row,
                                 'matches_selected_work_update_date':match,
                                 'identity_use':'prohibited_unresolved_source_author_id' if quarantine else 'not_identity_evidence'},
                                 ensure_ascii=False,default=str)+'\n')
                            count += 1
                        if table.name == 'works_referenced_works':
                            ref_idx = batch.schema.get_field_index('referenced_work_id')
                            edges = batch.filter(pc.is_in(batch.column(ref_idx),value_set=keys))
                            for edge in edges.to_pylist():
                                incoming.write(json.dumps({'citing':f"https://openalex.org/W{edge['id']}",
                                    'cited':f"https://openalex.org/W{edge['referenced_work_id']}",
                                    'source_record':edge, 'source_file':str(path),
                                    'coverage':'selected_update_partition_only_not_complete_citation_history'},
                                    default=str)+'\n')
                                counts['incoming_citation_records_partial'] += 1
            reports[table.name] = {'status':'scanned_selected_partition', 'rows':count}
    manifest['side_table_archive'] = reports
    manifest['limitations'].append('incoming citations cover one update partition only; not historical as-of visibility')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/opt/openalex'))
    parser.add_argument('--partition',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=Path(__file__).parent/'configs/pilot.json')
    parser.add_argument('--archive-side-tables',action='store_true',
                        help='Archive all work-level side-table rows for selected IDs in this partition; author IDs quarantined')
    args = parser.parse_args()
    result = pilot(args.root,args.partition,args.output,json.loads(args.config.read_text()),args.archive_side_tables)
    print(json.dumps({'output':str(args.output), 'status':result['status'], 'counts':result['counts'],
                      'sample_titles':result['sample_titles'], 'elapsed_seconds':result['elapsed_seconds']},indent=2,ensure_ascii=False))


if __name__ == '__main__': main()
