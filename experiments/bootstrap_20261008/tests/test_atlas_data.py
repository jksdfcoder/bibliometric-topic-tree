import copy
import datetime
import gzip
import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atlas_data import abstract, normalize, run, digest

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'configs/pilot.json').read_text())


def work(n=1, **kwargs):
    return {'id': f'https://openalex.org/W{n}', 'display_name': 'Bibliometric methods',
            'publication_date': '2023-01-01', 'updated_date': '2026-01-01T00:00:00Z', **kwargs}


class DataTests(unittest.TestCase):
    def test_time_uses_publication_not_discovery(self):
        for date, expected in [('2021-10-07', False), ('2021-10-08', True),
                               ('2026-10-08', True), ('2026-10-09', False), ('2001-01-01', False)]:
            row, _ = normalize(work(publication_date=date, created_date='2026-10-08'), CONFIG, 'test')
            self.assertEqual(row is not None, expected)
        row, _ = normalize(work(created_date='2026-10-08'), CONFIG, 'test')
        self.assertIsNone(row['first_discovered_date'])

    def test_topics_and_author_entities_never_control_selection(self):
        row, reason = normalize(work(display_name='unrelated paper', primary_topic={'display_name':'Bibliometrics'},
                               authorships=[{'author': {'id':'A1', 'display_name':'Bibliometric'}}]), CONFIG, 'test')
        self.assertIsNone(row)
        self.assertEqual(reason, 'no_scope_signal')

    def test_mentions_preserve_raw_and_change_with_byline(self):
        authors = [{'raw_author_name':'A. Lee', 'raw_affiliation_strings':['Raw unit'],
                    'author': {'id':'A123', 'display_name':'Alice Lee', 'orcid':'unproven'}}]
        row, _ = normalize(work(authorships=authors), CONFIG, 'test')
        self.assertEqual(row['mentions'][0]['raw_name'], 'A. Lee')
        self.assertNotIn('A123', json.dumps(row))
        self.assertNotIn('unproven', json.dumps(row))
        other, _ = normalize(work(authorships=[{'raw_author_name':'B'}, *authors]), CONFIG, 'test')
        self.assertNotEqual(row['mentions'][0]['mention_id'], other['mentions'][1]['mention_id'])

    def test_missing_abstract_and_reference_states(self):
        for refs, status in [(None,'missing'), ([], 'reported_empty'), (['W99','W99'], 'present')]:
            row, _ = normalize(work(referenced_works=refs), CONFIG, 'test')
            self.assertEqual(row['reference_status'], status)
            self.assertEqual(row['abstract_status'], 'missing')
            if refs: self.assertEqual(row['references'], ['https://openalex.org/W99'])

    def test_abstract_is_not_truncated_and_gaps_flagged(self):
        text, status = abstract({'abstract_inverted_index': {'later':[2], 'first':[0]}})
        self.assertEqual((text, status), ('first later', 'position_gaps'))
        long = 'word ' * 20000
        self.assertEqual(abstract({'abstract':long})[0], long)
        with self.assertRaises(ValueError):
            abstract({'abstract_inverted_index': {'a':[0], 'b':[0]}})

    def test_multilingual_scope_and_adjacent_review(self):
        row, _ = normalize(work(display_name='科研评价方法'), CONFIG, 'test')
        self.assertEqual(row['scope_evidence']['route'], 'adjacent_candidate')
        row, _ = normalize(work(display_name='The bibliometrics of medicine'), CONFIG, 'test')
        self.assertEqual(row['scope_evidence']['status'], 'candidate_only_requires_human_review')

    def test_versioned_run_dedup_counts_and_reproducibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'input.jsonl.gz'
            rows = [work(i, referenced_works=['W99']) for i in range(1, 8)]
            rows += [work(1, display_name='Bibliometric updated methods', updated_date='2026-02-01')]
            # Latest revision can leave scope; obsolete scoped revision must disappear.
            rows += [work(2, display_name='unrelated title', updated_date='2026-03-01')]
            config = {**CONFIG, 'pilot_per_stratum':2}
            with gzip.open(source,'wt') as stream:
                for row in rows: stream.write(json.dumps(row)+'\n')
            before = source.read_bytes()
            a = run(source, config, root/'a', 'unit-fixture')
            b = run(source, config, root/'b', 'unit-fixture')
            self.assertEqual(a['counts']['candidates'], 6)
            self.assertEqual(a['counts']['reference_edges'], 5)
            self.assertEqual(sum(v['works'] for v in a['strata'].values()), 6)
            self.assertEqual((root/'a/pilot.jsonl').read_bytes(), (root/'b/pilot.jsonl').read_bytes())
            self.assertEqual(source.read_bytes(), before)
            with self.assertRaises(FileExistsError): run(source, config, root/'a', 'unit-fixture')

    def test_conflicts_fail_with_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'input.jsonl'
            source.write_text('\n'.join(json.dumps(row) for row in [work(), work(display_name='Bibliometric revised')]))
            with self.assertRaisesRegex(ValueError, 'Conflicting versions'):
                run(source, CONFIG, root/'out', 'unit-fixture')
            self.assertEqual(json.loads((root/'out/manifest.json').read_text())['status'], 'failed')

    def test_native_parquet_path(self):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest('optional pyarrow unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'works.parquet'
            pq.write_table(pa.Table.from_pylist([work(1, publication_date=datetime.date(2023,1,1),
                      created_date=datetime.date(2026,1,1), referenced_works=['W99'])]), source)
            result = run(source, CONFIG, root/'out', 'unit-fixture')
            self.assertEqual(result['counts']['candidates'], 1)

    def test_arrow_map_and_precise_timestamp(self):
        row, _ = normalize(work(abstract_inverted_index=[('Bibliometric', [0]), ('research', [1])],
                                updated='2026-01-01T12:34:56Z'), CONFIG, 'test')
        self.assertEqual(row['abstract'], 'Bibliometric research')
        self.assertEqual(row['source_updated_date'], '2026-01-01T12:34:56Z')
        with self.assertRaisesRegex(ValueError, 'duplicate abstract map'):
            abstract({'abstract_inverted_index':[('a',[0]),('a',[1])]})

    def test_relational_partition_pilot_and_reference_version(self):
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError:
            self.skipTest('optional pyarrow unavailable')
        from lake_pilot import pilot
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'lake'
            (root/'works/2025-11-11').mkdir(parents=True)
            (root/'works_referenced_works/2025-11-11').mkdir(parents=True)
            schema = pa.schema([('id',pa.int64()),('title',pa.string()),('language',pa.string()),
                       ('publication_date',pa.date32()),('updated_date',pa.date32()),
                       ('updated',pa.timestamp('us',tz='UTC')),
                       ('abstract_inverted_index',pa.map_(pa.string(),pa.list_(pa.int32())))])
            row = {'id':1, 'title':'Bibliometric methods', 'language':'zh',
                   'publication_date':datetime.date(2023,1,1), 'updated_date':datetime.date(2025,11,11),
                   'updated':datetime.datetime(2025,11,11,12,tzinfo=datetime.timezone.utc),
                   'abstract_inverted_index':[('test',[0])]}
            pq.write_table(pa.Table.from_pylist([row],schema=schema),root/'works/2025-11-11/data_0.parquet')
            row['id']=2
            row['abstract_inverted_index']=None
            pq.write_table(pa.Table.from_pylist([row],schema=schema),root/'works/2025-11-11/data_1.parquet')
            edges=[{'id':1,'updated_date':datetime.date(2025,11,11),'referenced_work_id':99},
                   {'id':1,'updated_date':datetime.date(2025,11,11),'referenced_work_id':99},
                   {'id':2,'updated_date':datetime.date(2025,10,10),'referenced_work_id':100},
                   {'id':999,'updated_date':datetime.date(2025,11,11),'referenced_work_id':1}]
            pq.write_table(pa.Table.from_pylist(edges),root/'works_referenced_works/2025-11-11/data_0.parquet')
            out = Path(tmp)/'out'
            (root/'works_authorships/2025-11-11').mkdir(parents=True)
            pq.write_table(pa.Table.from_pylist([{'id':1,'author_id':123,
                           'updated_date':datetime.date(2025,11,11)}]),
                           root/'works_authorships/2025-11-11/data_0.parquet')
            result = pilot(root,'2025-11-11',out,CONFIG,archive_side_tables=True)
            self.assertEqual(result['counts']['candidates'],2)
            self.assertEqual(result['counts']['reference_edges'],1)
            self.assertEqual(result['counts']['reference_version_mismatch'],1)
            rows=[json.loads(line) for line in (out/'works.jsonl').read_text().splitlines()]
            self.assertEqual(rows[1]['reference_status'],'unknown_no_matching_rows')
            self.assertEqual(rows[0]['abstract'],'test')
            archived = json.loads((out/'source_archive/works.jsonl').read_text().splitlines()[0])
            self.assertEqual(archived['source_record']['language'],'zh')
            self.assertEqual(result['counts']['incoming_citation_records_partial'],1)
            self.assertTrue((out/'identity_source_quarantine/works_authorships.jsonl').is_file())
            self.assertFalse((out/'source_archive/works_authorships.jsonl').exists())
            self.assertNotIn('author_id',(out/'works.jsonl').read_text())

    def test_source_tree_cannot_be_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'works.jsonl').write_text(json.dumps(work())+'\n')
            with self.assertRaisesRegex(ValueError, 'outside'):
                run(root, CONFIG, root/'out', 'unit-fixture')


if __name__ == '__main__': unittest.main()
