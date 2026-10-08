"""Read-only scope extraction. No API calls, author entities or model training."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import datetime as dt
import gzip
import hashlib
import heapq
import json
from pathlib import Path
import platform
import re
import resource
import sqlite3
import subprocess
import time

VERSION = 'atlas-data-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     default=str).encode()).hexdigest()


def abstract(raw):
    direct = raw.get('abstract')
    if isinstance(direct, str) and direct.strip():
        return direct, 'present'
    index = raw.get('abstract_inverted_index')
    if not index:
        return None, 'missing'
    # PyArrow map columns become lists of (key, value) pairs in to_pylist().
    if isinstance(index, list):
        pairs = index
        try:
            index = dict(pairs)
        except (TypeError, ValueError) as exc:
            raise ValueError('invalid abstract map pairs') from exc
        if len(index) != len(pairs):
            raise ValueError('duplicate abstract map keys')
    if not isinstance(index, dict):
        raise ValueError('abstract_inverted_index must be an object')
    positions = {}
    for word, offsets in index.items():
        for offset in offsets:
            if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0 or offset in positions:
                raise ValueError('invalid/duplicate abstract position')
            positions[offset] = word
    if not positions:
        return None, 'missing'
    # Preserve available tokens; flag gaps, never invent words or silently truncate.
    status = 'position_gaps' if max(positions) + 1 != len(positions) else 'present'
    return ' '.join(positions[i] for i in sorted(positions)), status


def records(path, all_columns=False):
    if path.suffix == '.parquet':
        import pyarrow.parquet as pq
        parquet = pq.ParquetFile(path)
        names = set(parquet.schema_arrow.names)
        if not {'id', 'publication_date'} <= names:
            raise ValueError(f'{path}: not a works table; inspect relational schema first')
        wanted = {'id', 'display_name', 'title', 'publication_date', 'created_date', 'updated_date', 'updated',
                  'abstract', 'abstract_inverted_index', 'referenced_works', 'authorships',
                  'topics', 'primary_topic', 'primary_location', 'type', 'doi', 'is_retracted'}
        for batch in parquet.iter_batches(batch_size=4096, columns=None if all_columns else sorted(names & wanted)):
            yield from batch.to_pylist()
    else:
        opener = gzip.open if path.suffix == '.gz' else open
        with opener(path, 'rt', encoding='utf-8') as stream:
            for number, line in enumerate(stream, 1):
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError(f'{path}:{number}: expected work object')
                    yield row


def source_files(root):
    if not root.exists():
        raise FileNotFoundError(f'Input unavailable: {root}. No fallback download is performed.')
    files = [root] if root.is_file() else sorted(
        p for p in root.rglob('*') if p.is_file() and (
            p.suffix == '.parquet' or p.name.endswith(('.jsonl', '.jsonl.gz'))))
    if not files:
        raise ValueError('No JSONL/gz or Parquet inputs found')
    return files


def work_id(value):
    # Numeric IDs explicitly map to OpenAlex work namespace, never author namespace.
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return f'https://openalex.org/W{value}'
    if isinstance(value, str) and re.fullmatch(r'(?:https://openalex.org/)?W[0-9]+', value):
        return value if value.startswith('https://') else 'https://openalex.org/' + value
    raise ValueError(f'Invalid OpenAlex work ID: {value!r}')


def matched_terms(text, terms):
    text = text.casefold()
    return [term for term in terms if (re.search(r'(?<!\w)' + re.escape(term.casefold()) + r'\w*', text)
            if term.isascii() else term.casefold() in text)]


def normalize(raw, config, version):
    date = raw.get('publication_date')
    if date is None:
        return None, 'missing_publication_date'
    try:
        published = dt.date.fromisoformat(str(date))
    except ValueError:
        return None, 'invalid_publication_date'
    if not dt.date.fromisoformat(config['start_date']) <= published <= dt.date.fromisoformat(config['end_date']):
        return None, 'outside_window'
    wid = work_id(raw.get('id'))
    title = raw.get('title') or raw.get('display_name') or ''
    if not isinstance(title, str):
        raise ValueError('title must be text')
    text, status = abstract(raw)
    joined = title + '\n' + (text or '')
    core = matched_terms(joined, config['core_terms'])
    adjacent = matched_terms(joined, config['adjacent_terms'])
    location = raw.get('primary_location') or {}
    source_name = (location.get('source') or {}).get('display_name') or ''
    source_match = source_name.casefold() in {s.casefold() for s in config['candidate_sources']}
    if not (core or adjacent or source_match):
        return None, 'no_scope_signal'
    route = 'core_term_candidate' if core else 'adjacent_candidate' if adjacent else 'source_candidate'
    refs_raw = raw.get('referenced_works')
    if refs_raw is not None and not isinstance(refs_raw, list):
        raise ValueError('referenced_works must be a list or null')
    refs = sorted({work_id(r) for r in (refs_raw or [])})
    ref_status = 'missing' if refs_raw is None else 'reported_empty' if not refs else 'present'
    mentions = []
    for position, auth in enumerate(raw.get('authorships') or []):
        # Never fall back to author.display_name, author.id, author.orcid or resolved institutions.
        content = {'raw_name': auth.get('raw_author_name'),
                   'raw_affiliation_strings': auth.get('raw_affiliation_strings'),
                   'position_index': position, 'author_position': auth.get('author_position')}
        mentions.append({'mention_id': 'm:' + digest([wid, content]), 'work_id': wid,
                         'source_version': version, 'provenance': 'work.authorships.raw_fields', **content})
    return {'work_id': wid, 'source_id': wid, 'title': title or None, 'abstract': text,
            'abstract_status': status, 'publication_date': str(published),
            'first_discovered_date': None, 'source_created_date': str(raw['created_date']) if raw.get('created_date') else None,
            'source_updated_date': str(raw.get('updated') or raw['updated_date']) if (raw.get('updated') or raw.get('updated_date')) else None,
            'source_version': version, 'input_hash': digest({'title': title, 'abstract': text}),
            'raw_record_hash': digest(raw), 'type': raw.get('type'), 'doi': raw.get('doi'),
            'is_retracted': raw.get('is_retracted'), 'reference_status': ref_status,
            'references': refs, 'mentions': mentions,
            'openalex_topics_reference': {'topics': raw.get('topics'), 'primary_topic': raw.get('primary_topic')},
            'scope_evidence': {'route': route, 'terms': core + adjacent, 'source': source_name,
                               'status': 'candidate_only_requires_human_review'}}, None


def update_key(value):
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed.astimezone(dt.timezone.utc)


def run(root, config, output, version):
    started = time.monotonic()
    files = source_files(root)
    for key in ('start_date', 'end_date'):
        dt.date.fromisoformat(config[key])
    if config['start_date'] > config['end_date'] or config['pilot_per_stratum'] < 1:
        raise ValueError('invalid window or pilot size')
    output = output.resolve()
    if root.resolve() == output or (root.is_dir() and root.resolve() in output.parents):
        raise ValueError('Output must be outside the read-only source tree')
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'status': 'running', 'adapter_version': VERSION, 'source_version': version,
                'config': config, 'config_hash': digest(config), 'platform': platform.platform(),
                'created_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'output': str(output)}
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).parent,
                                capture_output=True, text=True, check=False).stdout.strip()
        manifest['code_commit'] = commit or None
        manifest['code_hash'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        stats, strata, heaps = Counter(), defaultdict(Counter), defaultdict(list)
        with sqlite3.connect(output / 'candidate_spool.sqlite') as db:
            db.execute('CREATE TABLE works (id TEXT PRIMARY KEY, payload TEXT)')
            inputs = []
            for path in files:
                before = path.stat()
                hasher = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        hasher.update(chunk)
                for raw in records(path):
                    stats['scanned'] += 1
                    row, reason = normalize(raw, config, version)
                    if reason:
                        stats[reason] += 1
                        row = {'work_id': work_id(raw.get('id')), 'excluded_reason': reason,
                               'raw_record_hash': digest(raw),
                               'source_updated_date': str(raw['updated_date']) if raw.get('updated_date') else None}
                    prior = db.execute('SELECT payload FROM works WHERE id=?', (row['work_id'],)).fetchone()
                    if prior:
                        old = json.loads(prior[0])
                        stats['duplicate_records'] += 1
                        if old['raw_record_hash'] == row['raw_record_hash']:
                            continue
                        a, b = update_key(old['source_updated_date']), update_key(row['source_updated_date'])
                        if a is None or b is None or a == b:
                            raise ValueError('Conflicting versions without ordered updated_date: ' + row['work_id'])
                        if a > b:
                            continue
                    db.execute('INSERT OR REPLACE INTO works VALUES (?,?)',
                               (row['work_id'], json.dumps(row, ensure_ascii=False, default=str)))
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('Source changed during extraction: ' + str(path))
                inputs.append({'path': str(path.resolve()), 'sha256': hasher.hexdigest(),
                               'bytes': before.st_size, 'mtime_ns': before.st_mtime_ns})
            db.commit()
            with (output / 'works.jsonl').open('w') as works, (output / 'references.jsonl').open('w') as refs, (output / 'mentions.jsonl').open('w') as mentions:
                for (payload,) in db.execute('SELECT payload FROM works ORDER BY id'):
                    row = json.loads(payload)
                    if row.get('excluded_reason'):
                        continue
                    stratum = '|'.join([row['publication_date'][:4], row['abstract_status'],
                                        row['reference_status'], row['scope_evidence']['route']])
                    strata[stratum]['works'] += 1
                    strata[stratum]['raw_name_mentions'] += sum(bool(m['raw_name']) for m in row['mentions'])
                    stats['candidates'] += 1
                    for field in ('abstract', 'source_updated_date', 'title'):
                        stats['missing_' + field] += not bool(row[field])
                    stats['references_' + row['reference_status']] += 1
                    for ref in row.pop('references'):
                        refs.write(json.dumps({'citing': row['work_id'], 'cited': ref, 'source_version': version,
                                               'evidence': 'direct_reference'}) + '\n')
                        stats['reference_edges'] += 1
                    for mention in row.pop('mentions'):
                        mentions.write(json.dumps(mention, ensure_ascii=False) + '\n')
                    works.write(json.dumps(row, ensure_ascii=False) + '\n')
                    score = int(digest([config['seed'], row['work_id']]), 16)
                    heap = heaps[stratum]
                    item = (-score, row['work_id'], row)
                    heapq.heappush(heap, item)
                    if len(heap) > config['pilot_per_stratum']:
                        heapq.heappop(heap)
            with (output / 'pilot.jsonl').open('w') as stream:
                for key in sorted(heaps):
                    for _, _, row in sorted(heaps[key], key=lambda item: item[1]):
                        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                        stats['pilot_works'] += 1
        manifest.update(status='completed', input_files=inputs, counts=dict(stats),
                        resources={'process_peak_rss_native': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                   'rss_unit': 'bytes' if platform.system() == 'Darwin' else 'KiB',
                                   'cpu_seconds': resource.getrusage(resource.RUSAGE_SELF).ru_utime + resource.getrusage(resource.RUSAGE_SELF).ru_stime},
                        strata={k:dict(v) for k,v in sorted(strata.items())},
                        elapsed_seconds=time.monotonic() - started,
                        limitations=['scope recall not measured', 'scope candidates not verified core topics',
                                     'external references retained but target metadata not fetched',
                                     'relational side-table joins require schema inspection',
                                     'no independent relevance labels or model accuracy'])
    except Exception as exc:
        manifest.update(status='failed', error=str(exc), elapsed_seconds=time.monotonic() - started)
        raise
    finally:
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    inspect = sub.add_parser('inspect')
    inspect.add_argument('--input', required=True, type=Path)
    extract = sub.add_parser('extract')
    extract.add_argument('--input', required=True, type=Path)
    extract.add_argument('--config', type=Path, default=Path(__file__).parent / 'configs/pilot.json')
    extract.add_argument('--output', required=True, type=Path)
    extract.add_argument('--source-version', required=True)
    args = parser.parse_args()
    if args.command == 'inspect':
        for path in source_files(args.input):
            if path.suffix == '.parquet':
                import pyarrow.parquet as pq
                p = pq.ParquetFile(path)
                print(json.dumps({'path': str(path), 'rows': p.metadata.num_rows, 'schema': str(p.schema_arrow)}))
            else:
                row = next(records(path), {})
                print(json.dumps({'path': str(path), 'first_record_fields': sorted(row)}))
    else:
        result = run(args.input, json.loads(args.config.read_text()), args.output, args.source_version)
        print(json.dumps({'status': result['status'], 'counts': result['counts'], 'output': result['output']}))


if __name__ == '__main__':
    main()
