import datetime as dt
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover - exercised only without pyarrow
    pa = pq = None

from atlas.data.inventory import (
    MANIFEST_NAMES,
    inspect_source,
    measure_local_environment,
    write_access_failure,
)

REPO = Path(__file__).resolve().parents[3]
SOURCE_CONFIG = REPO / "configs" / "data" / "source.json"
PROBE = REPO / "scripts" / "probe_source.py"
T1 = dt.datetime(2025, 11, 11, 12, 0, tzinfo=dt.timezone.utc)
T2 = dt.datetime(2025, 11, 12, 8, 30, tzinfo=dt.timezone.utc)
ENTITY = "ENTITY_NAME_QED_9913"
VENUE = "VENUE_NAME_QED_4421"


def need_arrow(test):
    if pq is None:
        test.skipTest("pyarrow unavailable")


def write_rows(path, rows, schema, statistics=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, write_statistics=statistics)


def work_schema():
    return pa.schema([
        ("id", pa.int64()),
        ("title", pa.string()),
        ("publication_date", pa.date32()),
        ("updated_date", pa.date32()),
        ("updated", pa.timestamp("us", tz="UTC")),
    ])


def work(row_id, stamp, title="t"):
    return {
        "id": row_id,
        "title": title,
        "publication_date": dt.date(2023, 1, 1),
        "updated_date": stamp.date(),
        "updated": stamp,
    }


def ref_schema():
    return pa.schema([
        ("id", pa.int64()),
        ("updated_date", pa.date32()),
        ("updated", pa.timestamp("us", tz="UTC")),
        ("referenced_work_id", pa.int64()),
    ])


def ref(row_id, stamp, cited=9):
    return {
        "id": row_id,
        "updated_date": stamp.date(),
        "updated": stamp,
        "referenced_work_id": cited,
    }


def write_snapshot(root, **overrides):
    doc = {
        "source_version": "fixture-snapshot-9",
        "partition_role": "update",
        "reference_set_semantics": "same work id and the same updated timestamp, regardless of partition directory",
        "deletion_semantics": "no delete log shipped; a missing id is not evidence of deletion",
        "empty_side_table_semantics": "a missing side table or a zero-row file is unknown_no_rows, not reported_empty",
    }
    doc.update(overrides)
    (root / "snapshot_manifest.json").write_text(json.dumps(doc))
    return doc


def fields_by_name(result):
    return {item["field"]: item for item in result["fields"]}


class InventoryTests(unittest.TestCase):
    def test_missing_source_never_falls_back_to_download(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "output"
            with self.assertRaises(FileNotFoundError) as caught:
                inspect_source(Path(d) / "absent", output)
            self.assertIn("No fallback download", str(caught.exception))
            self.assertFalse(output.exists())

    def test_file_root_is_not_treated_as_a_lake(self):
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "file.parquet"
            lake.write_text("not a directory")
            with self.assertRaises(NotADirectoryError):
                inspect_source(lake, Path(d) / "output")

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            lake.mkdir()
            output = Path(d) / "output"
            output.mkdir()
            (output / "source_manifest.json").write_text("keep")
            with self.assertRaises(FileExistsError):
                inspect_source(lake, output)
            self.assertEqual((output / "source_manifest.json").read_text(), "keep")

    def test_output_inside_source_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            lake.mkdir()
            with self.assertRaisesRegex(ValueError, "outside"):
                inspect_source(lake, lake / "output")
            self.assertFalse((lake / "output").exists())

    def test_source_config_rejects_download_and_names_manifests(self):
        cfg = json.loads(SOURCE_CONFIG.read_text())
        self.assertFalse(cfg["download_on_missing"])
        self.assertIsNone(cfg["source_version"])
        self.assertEqual(list(MANIFEST_NAMES), cfg["recognized_manifest_filenames"])
        self.assertGreaterEqual(cfg["sample_rows_per_file"], 1)

    def test_empty_root_is_blocked_without_fake_measurements(self):
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            lake.mkdir()
            result = inspect_source(lake, Path(d) / "output")
            self.assertEqual(result["status"], "blocked")
            self.assertIsNone(result["source_version"])
            self.assertFalse(result["source_version_fixed"])
            self.assertFalse(result["normalized_references_allowed"])
            self.assertFalse(result["tables"]["works"]["present"])
            self.assertIsNone(result["tables"]["works"]["rows"])
            self.assertIsNone(result["tables"]["works"]["file_count"])
            self.assertIsNone(result["coverage"]["publication_date"])
            self.assertIsNone(result["coverage"]["abstract"])
            self.assertIsNone(result["coverage"]["references"])
            self.assertEqual(result["partition_role"], "unknown")
            self.assertFalse(result["runtime"]["spark_confirmed"])
            self.assertIsNone(result["runtime"]["step_time_seconds"])
            self.assertFalse(result["runtime"]["clock_ratio_used_as_step_time"])
            self.assertEqual(result["runtime"]["lake_host_role"], "unverified")
            self.assertNotIn("gpu_clock_mhz_reported", result["runtime"])
            self.assertIn("snapshot_or_conversion_manifest", result["missing_inputs"])
            self.assertIn("coverage_not_measured", result["limitations"])
            self.assertNotIn("audit_complete_does_not_mean_coverage_complete", result["limitations"])

    def test_run_manifest_records_blocked_audit_without_a_fake_version(self):
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            lake.mkdir()
            output = Path(d) / "output"
            result = inspect_source(lake, output)
            self.assertEqual(json.loads((output / "inventory.json").read_text()), result)
            manifest = json.loads((output / "source_manifest.json").read_text())
            for key in ("run_id", "status", "stage", "code", "data", "config", "models", "resources", "outputs", "limitations"):
                self.assertIn(key, manifest)
            self.assertEqual(manifest["status"], "blocked")
            self.assertEqual(manifest["stage"], "source_audit")
            self.assertEqual(manifest["run_id"], "output")
            self.assertEqual(manifest["data"]["source_version"], "unverified")
            self.assertFalse(manifest["data"]["source_version_fixed"])
            self.assertFalse(manifest["normalized_references_allowed"])
            self.assertEqual(manifest["models"], [])
            self.assertFalse(manifest["config"]["resolved"]["download_on_missing"])
            self.assertRegex(manifest["code"]["content_hash"], r"^[0-9a-f]{64}$")
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True,
            ).stdout.strip()
            self.assertEqual(manifest["code"]["commit"], head)
            digest = hashlib.sha256((output / "inventory.json").read_bytes()).hexdigest()
            recorded = {item["path"]: item["hash"] for item in manifest["outputs"]}
            self.assertEqual(recorded["inventory.json"], digest)
            self.assertIn("coverage_not_measured", manifest["limitations"])

    def test_every_shard_is_counted_across_partitions(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            schema = work_schema()
            write_rows(lake / "works" / "2020-08-21" / "data_0.parquet", [work(1, T1), work(2, T1)], schema)
            write_rows(lake / "works" / "2025-11-11" / "data_0.parquet", [work(3, T2)], schema)
            write_rows(lake / "works" / "2025-11-11" / "data_1.parquet", [work(n, T2) for n in range(4, 8)], schema)
            result = inspect_source(lake, Path(d) / "output")
            works = result["tables"]["works"]
            by_path = {item["path"]: item["rows"] for item in works["files"]}
            self.assertEqual(by_path["2020-08-21/data_0.parquet"], 2)
            self.assertEqual(by_path["2025-11-11/data_0.parquet"], 1)
            self.assertEqual(by_path["2025-11-11/data_1.parquet"], 4)
            self.assertEqual(works["file_count"], 3)
            self.assertEqual(works["rows"], 7)
            self.assertEqual(works["partitions"], ["2020-08-21", "2025-11-11"])
            self.assertIsNone(result["source_version"])
            self.assertNotEqual(result["source_version"], "2025-11-11")
            self.assertEqual(result["partition_role"], "unknown")
            directories = [item for item in result["source_version_candidates"] if item["kind"] == "partition_directory"]
            self.assertEqual(sorted(item["value"] for item in directories), ["2020-08-21", "2025-11-11"])
            self.assertTrue(all(item["selected"] is False for item in result["source_version_candidates"]))
            self.assertFalse(result["normalized_references_allowed"])
            self.assertEqual(result["reference_join"]["state"], "unknown_no_rows")
            self.assertIsNone(result["tables"]["works_referenced_works"]["rows"])
            self.assertIsNone(result["tables"]["works_referenced_works"]["file_count"])
            self.assertTrue(works["column_statistics_present"]["publication_date"])
            self.assertIsNone(result["coverage"]["publication_date"])
            self.assertIn("directory_dates_are_not_snapshot_dates", result["limitations"])
            self.assertIn("snapshot_or_conversion_manifest", result["missing_inputs"])

    def test_schema_differences_across_shards_are_reported(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            plain = pa.schema([("id", pa.int64()), ("title", pa.string())])
            wider = pa.schema([("id", pa.int64()), ("title", pa.string()), ("language", pa.string())])
            write_rows(lake / "works" / "part" / "data_0.parquet", [{"id": 1, "title": "t"}], plain)
            write_rows(lake / "works" / "part" / "data_1.parquet", [{"id": 2, "title": "t", "language": "zh"}], wider)
            result = inspect_source(lake, Path(d) / "output")
            groups = {}
            for group in result["tables"]["works"]["schema_groups"]:
                groups[tuple(col["name"] for col in group["columns"])] = group["files"]
            self.assertEqual(groups[("id", "title")], ["part/data_0.parquet"])
            self.assertEqual(groups[("id", "language", "title")], ["part/data_1.parquet"])
            self.assertTrue(result["tables"]["works"]["schema_differs"])
            self.assertEqual(result["tables"]["works"]["file_count"], 2)

    def test_corrupt_shard_does_not_invent_a_table_total(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            write_rows(lake / "works" / "part" / "data_0.parquet", [work(1, T1), work(2, T1)], work_schema())
            bad = lake / "works" / "part" / "data_1.parquet"
            bad.parent.mkdir(parents=True, exist_ok=True)
            bad.write_bytes(b"not parquet")
            result = inspect_source(lake, Path(d) / "output")
            files = {item["path"]: item for item in result["tables"]["works"]["files"]}
            self.assertEqual(result["tables"]["works"]["file_count"], 2)
            self.assertEqual(files["part/data_0.parquet"]["rows"], 2)
            self.assertIsNone(files["part/data_1.parquet"]["rows"])
            self.assertTrue(files["part/data_1.parquet"]["error"])
            self.assertIsNone(result["tables"]["works"]["rows"])
            self.assertEqual(result["status"], "blocked")
            self.assertIn("unreadable_parquet", result["missing_inputs"])

    def test_disabled_column_statistics_do_not_become_coverage(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            write_rows(
                lake / "works" / "part" / "data_0.parquet",
                [work(1, T1)],
                work_schema(),
                statistics=False,
            )
            result = inspect_source(lake, Path(d) / "output")
            self.assertFalse(result["tables"]["works"]["column_statistics_present"]["publication_date"])
            self.assertFalse(result["tables"]["works"]["column_statistics_present"]["updated"])
            self.assertIsNone(result["coverage"]["publication_date"])
            self.assertIsNone(result["coverage"]["abstract"])

    def test_missing_reference_table_is_unknown_not_empty(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            write_rows(lake / "works" / "part" / "data_0.parquet", [work(1, T1)], work_schema())
            result = inspect_source(lake, Path(d) / "output")
            side = result["tables"]["works_referenced_works"]
            self.assertFalse(side["present"])
            self.assertIsNone(side["rows"])
            self.assertIsNone(side["file_count"])
            self.assertEqual(result["reference_join"]["state"], "unknown_no_rows")
            self.assertNotEqual(result["reference_join"]["state"], "reported_empty")
            self.assertFalse(result["normalized_references_allowed"])
            self.assertIn("reference_side_table", result["missing_inputs"])

    def test_zero_row_reference_file_is_not_reported_empty(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            write_rows(lake / "works" / "part" / "data_0.parquet", [work(1, T1)], work_schema())
            write_rows(lake / "works_referenced_works" / "part" / "data_0.parquet", [], ref_schema())
            result = inspect_source(lake, Path(d) / "output")
            side = result["tables"]["works_referenced_works"]
            self.assertEqual(side["file_count"], 1)
            self.assertEqual(side["rows"], 0)
            self.assertEqual(result["reference_join"]["state"], "unknown_no_rows")
            self.assertNotEqual(result["reference_join"]["state"], "reported_empty")
            self.assertGreaterEqual(result["reference_join"]["no_side_rows"], 1)
            self.assertFalse(result["normalized_references_allowed"])
            self.assertIsNone(result["source_version"])

    def test_directory_dates_and_equal_dates_do_not_fix_a_version(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            schema = pa.schema([("id", pa.int64()), ("updated_date", pa.date32())])
            row = {"id": 1, "updated_date": dt.date(2025, 11, 11)}
            write_rows(lake / "works" / "2025-11-11" / "data_0.parquet", [row], schema)
            write_rows(lake / "works_referenced_works" / "2025-11-11" / "data_0.parquet", [row], schema)
            write_snapshot(lake)
            result = inspect_source(lake, Path(d) / "output")
            self.assertEqual(result["reference_join"]["same_date_diagnostic"], 1)
            self.assertEqual(result["reference_join"]["same_timestamp"], 0)
            self.assertEqual(result["reference_join"]["state"], "unproven")
            self.assertIsNone(result["source_version"])
            self.assertFalse(result["source_version_fixed"])
            self.assertFalse(result["normalized_references_allowed"])
            self.assertEqual(result["status"], "blocked")
            self.assertNotEqual(result["source_version"], "2025-11-11")
            self.assertIn("reference_version_unproven", result["missing_inputs"])
            manifest_candidates = [item for item in result["source_version_candidates"] if item["kind"] == "snapshot_manifest"]
            self.assertEqual(manifest_candidates, [{"value": "fixture-snapshot-9", "kind": "snapshot_manifest", "selected": False}])

    def test_date_versus_timestamp_is_not_the_same_version(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            write_rows(lake / "works" / "part" / "data_0.parquet", [work(1, T1)], work_schema())
            date_only = pa.schema([("id", pa.int64()), ("updated_date", pa.date32())])
            write_rows(
                lake / "works_referenced_works" / "part" / "data_0.parquet",
                [{"id": 1, "updated_date": dt.date(2025, 11, 11)}],
                date_only,
            )
            write_snapshot(lake)
            result = inspect_source(lake, Path(d) / "output")
            self.assertGreaterEqual(result["reference_join"]["precision_mismatch"], 1)
            self.assertEqual(result["reference_join"]["same_timestamp"], 0)
            self.assertEqual(result["reference_join"]["state"], "version_conflict")
            self.assertFalse(result["normalized_references_allowed"])
            self.assertIsNone(result["source_version"])
            self.assertIn("reference_version_conflict", result["missing_inputs"])

    def test_timestamp_mismatch_blocks_normalized_references(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            write_rows(
                lake / "works" / "part" / "data_0.parquet",
                [work(1, T1), work(2, T2)],
                work_schema(),
            )
            write_rows(
                lake / "works_referenced_works" / "part" / "data_0.parquet",
                [ref(1, T2, 9), ref(2, T2, 8)],
                ref_schema(),
            )
            write_snapshot(lake)
            result = inspect_source(lake, Path(d) / "output")
            self.assertGreaterEqual(result["reference_join"]["same_timestamp"], 1)
            self.assertGreaterEqual(result["reference_join"]["different_timestamp"], 1)
            self.assertEqual(result["reference_join"]["state"], "version_conflict")
            self.assertFalse(result["normalized_references_allowed"])
            self.assertIsNone(result["source_version"])
            self.assertFalse(result["source_version_fixed"])
            self.assertEqual(result["status"], "blocked")
            self.assertIn("reference_version_conflict", result["missing_inputs"])

    def test_cross_partition_timestamp_conflict_blocks_version(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            schema = work_schema()
            write_rows(lake / "works" / "2020-08-21" / "data_0.parquet", [work(1, T1)], schema)
            write_rows(lake / "works" / "2025-11-11" / "data_0.parquet", [work(1, T2)], schema)
            write_rows(lake / "works_referenced_works" / "2025-11-11" / "data_0.parquet", [ref(1, T2)], ref_schema())
            write_snapshot(lake)
            result = inspect_source(lake, Path(d) / "output")
            self.assertGreaterEqual(result["reference_join"]["cross_partition_conflicts"], 1)
            self.assertEqual(result["reference_join"]["state"], "version_conflict")
            self.assertIsNone(result["source_version"])
            self.assertFalse(result["normalized_references_allowed"])
            self.assertEqual(result["partition_role"], "unknown")
            self.assertIn("2020-08-21", result["tables"]["works"]["partitions"])
            self.assertIn("2025-11-11", result["tables"]["works"]["partitions"])

    def test_duplicate_work_id_in_one_partition_blocks_version(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            write_rows(lake / "works" / "part" / "data_0.parquet", [work(1, T1), work(1, T2)], work_schema())
            write_rows(lake / "works_referenced_works" / "part" / "data_0.parquet", [ref(1, T2)], ref_schema())
            write_snapshot(lake)
            result = inspect_source(lake, Path(d) / "output")
            self.assertGreaterEqual(result["reference_join"]["duplicate_ids_same_partition"], 1)
            self.assertIsNone(result["source_version"])
            self.assertFalse(result["normalized_references_allowed"])
            self.assertIn("duplicate_work_ids", result["missing_inputs"])

    def test_author_entity_names_are_not_copied_and_source_ids_stay_unresolved(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            write_rows(lake / "works" / "part" / "data_0.parquet", [work(1, T1, title="TITLE_SHOULD_NOT_LEAK_7781")], work_schema())
            write_rows(
                lake / "works_authorships" / "part" / "data_0.parquet",
                [{"id": 1, "updated_date": dt.date(2025, 11, 11), "author_position": "first", "author_id": 12345}],
                pa.schema([
                    ("id", pa.int64()),
                    ("updated_date", pa.date32()),
                    ("author_position", pa.string()),
                    ("author_id", pa.int64()),
                ]),
            )
            write_rows(
                lake / "works_authorships_affiliations" / "part" / "data_0.parquet",
                [{"id": 1, "author_position": "first", "institution_id": 99}],
                pa.schema([
                    ("id", pa.int64()),
                    ("author_position", pa.string()),
                    ("institution_id", pa.int64()),
                ]),
            )
            write_rows(
                lake / "authors" / "data_0.parquet",
                [{"id": 12345, "display_name": ENTITY}],
                pa.schema([("id", pa.int64()), ("display_name", pa.string())]),
            )
            write_rows(
                lake / "sources" / "data_0.parquet",
                [{"id": 7, "display_name": VENUE}],
                pa.schema([("id", pa.int64()), ("display_name", pa.string())]),
            )
            output = Path(d) / "output"
            result = inspect_source(lake, output)
            blob = json.dumps(result)
            stored = (output / "inventory.json").read_text()
            self.assertNotIn(ENTITY, blob)
            self.assertNotIn(VENUE, blob)
            self.assertNotIn("TITLE_SHOULD_NOT_LEAK_7781", blob)
            self.assertNotIn(ENTITY, stored)
            self.assertNotIn(VENUE, stored)
            self.assertFalse(result["raw_mentions"]["filled_from_author_entity"])
            self.assertFalse(result["raw_mentions"]["raw_name_observed"])
            self.assertFalse(result["raw_mentions"]["raw_affiliation_observed"])
            self.assertFalse(result["author_entity_values_read"])
            self.assertEqual(result["author_entity_values_read"], False)
            named = fields_by_name(result)
            self.assertEqual(named["raw_name"]["observed_columns"], [])
            self.assertEqual(named["raw_name"]["version_basis"], "unverified")
            self.assertEqual(named["raw_affiliation"]["observed_columns"], [])
            self.assertEqual(named["source_name"]["observed_columns"], ["display_name"])
            self.assertTrue(result["source_dimension_readable"])
            self.assertFalse(result["source_ids_resolved_to_names"])
            self.assertEqual(result["tables"]["authors"]["value_rows_read"], 0)

    def test_complete_evidence_fixes_manifest_version_not_directory_date(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            schema = work_schema()
            write_rows(lake / "works" / "2020-08-21" / "data_0.parquet", [work(1, T1)], schema)
            write_rows(lake / "works" / "2025-11-11" / "data_0.parquet", [work(1, T1), work(2, T2)], schema)
            write_rows(
                lake / "works_referenced_works" / "2025-11-11" / "data_0.parquet",
                [ref(1, T1, 9), ref(2, T2, 8)],
                ref_schema(),
            )
            write_snapshot(lake)
            output = Path(d) / "output"
            result = inspect_source(lake, output)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["source_version"], "fixture-snapshot-9")
            self.assertNotEqual(result["source_version"], "2025-11-11")
            self.assertTrue(result["source_version_fixed"])
            self.assertTrue(result["normalized_references_allowed"])
            self.assertEqual(result["partition_role"], "update")
            self.assertEqual(result["partition_role_basis"], "snapshot_manifest")
            self.assertEqual(result["reference_join"]["state"], "consistent_timestamp")
            self.assertEqual(result["reference_join"]["same_timestamp"], 3)
            self.assertEqual(result["reference_join"]["different_timestamp"], 0)
            self.assertEqual(result["reference_join"]["no_side_rows"], 0)
            self.assertTrue(result["reference_join"]["sample_complete"])
            self.assertEqual(result["missing_inputs"], [])
            self.assertIsNone(result["coverage"]["publication_date"])
            self.assertIsNone(result["coverage"]["references"])
            self.assertIsNone(result["coverage"]["raw_name"])
            self.assertIn("coverage_not_measured", result["limitations"])
            self.assertIn("audit_complete_does_not_mean_coverage_complete", result["limitations"])
            self.assertEqual(fields_by_name(result)["title"]["version_basis"], "fixture-snapshot-9")
            self.assertEqual(fields_by_name(result)["referenced_work_id"]["observed_columns"], ["referenced_work_id"])
            manifest = json.loads((output / "source_manifest.json").read_text())
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["data"]["source_version"], "fixture-snapshot-9")
            self.assertTrue(manifest["data"]["source_version_fixed"])
            directories = [item for item in result["source_version_candidates"] if item["kind"] == "partition_directory"]
            self.assertTrue(all(item["selected"] is False for item in directories))

    def test_two_manifests_do_not_fix_a_version(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            write_rows(lake / "works" / "part" / "data_0.parquet", [work(1, T1)], work_schema())
            write_rows(lake / "works_referenced_works" / "part" / "data_0.parquet", [ref(1, T1)], ref_schema())
            write_snapshot(lake)
            (lake / "conversion_manifest.json").write_text(json.dumps({"source_version": "other-snapshot"}))
            result = inspect_source(lake, Path(d) / "output")
            self.assertIsNone(result["source_version"])
            self.assertFalse(result["normalized_references_allowed"])
            self.assertEqual(result["status"], "blocked")
            self.assertIn("unique_snapshot_manifest", result["missing_inputs"])

    def test_capped_sample_cannot_fix_source_version(self):
        need_arrow(self)
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            cap = json.loads(SOURCE_CONFIG.read_text())["sample_rows_per_file"]
            total = cap + 1
            schema = work_schema()
            write_rows(
                lake / "works" / "part" / "data_0.parquet",
                [work(i, T1) for i in range(1, total + 1)],
                schema,
            )
            write_rows(
                lake / "works_referenced_works" / "part" / "data_0.parquet",
                [ref(i, T1, 1000 + i) for i in range(1, total + 1)],
                ref_schema(),
            )
            write_snapshot(lake)
            result = inspect_source(lake, Path(d) / "output")
            self.assertEqual(result["tables"]["works"]["rows"], total)
            self.assertFalse(result["reference_join"]["sample_complete"])
            self.assertIsNone(result["source_version"])
            self.assertFalse(result["normalized_references_allowed"])
            self.assertEqual(result["status"], "blocked")
            self.assertIn("reference_sample_incomplete", result["missing_inputs"])

    def test_access_failure_record_does_not_invent_counts(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "source-audit-001"
            with self.assertRaises(FileNotFoundError) as caught:
                inspect_source(Path(d) / "absent", output)
            self.assertFalse(output.exists())
            record = write_access_failure(output, caught.exception)
            self.assertEqual(record["status"], "blocked")
            self.assertIsNone(record["source_version"])
            self.assertFalse(record["normalized_references_allowed"])
            self.assertIsNone(record["inventory"]["rows"])
            self.assertIsNone(record["inventory"]["coverage"])
            self.assertIsNone(record["inventory"]["schema_samples"])
            self.assertFalse(record["inventory"]["measured"])
            manifest = json.loads((output / "source_manifest.json").read_text())
            self.assertEqual(manifest["status"], "blocked")
            self.assertIn("FileNotFoundError", manifest["error"])
            self.assertIn("No fallback download", manifest["error"])
            self.assertIn("readable_lake_root", manifest["missing_inputs"])
            stored = (output / "inventory.json").read_text() + (output / "source_manifest.json").read_text()
            self.assertNotRegex(stored, r'"rows":\s*0')
            self.assertNotRegex(stored, r'"schema_samples":\s*\[')

    def test_local_environment_is_not_a_spark_measurement(self):
        env = measure_local_environment()
        self.assertFalse(env["spark_confirmed"])
        self.assertEqual(env["host_role"], "local_audit_process")
        self.assertEqual(env["lake_host_role"], "unverified")
        self.assertIsNone(env["step_time_seconds"])
        self.assertFalse(env["clock_ratio_used_as_step_time"])
        self.assertFalse(env["service_shutdown"])
        self.assertNotIn("gpu_clock_mhz_reported", env)
        self.assertEqual(env["evidence_class"], "measured_local_process")
        self.assertIn("pyarrow", env["modules"])

    def test_probe_script_records_blocked_when_root_missing(self):
        with tempfile.TemporaryDirectory() as d:
            missing = Path(d) / "absent"
            output = Path(d) / "source-audit-001"
            proc = subprocess.run(
                [sys.executable, str(PROBE), "--root", str(missing), "--output", str(output)],
                cwd=REPO,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn("blocked", proc.stdout)
            self.assertIn("No fallback download", proc.stderr)
            manifest = json.loads((output / "source_manifest.json").read_text())
            inventory = json.loads((output / "inventory.json").read_text())
            self.assertEqual(manifest["status"], "blocked")
            self.assertIsNone(inventory["rows"])
            self.assertIsNone(inventory["schema_samples"])
            self.assertIsNone(inventory["coverage"])
            env = json.loads((output / "environment.json").read_text())
            self.assertFalse(env["spark_confirmed"])
            self.assertEqual(env["lake_host_role"], "unverified")
            self.assertIsNone(env["step_time_seconds"])
            self.assertFalse(env["service_shutdown"])

    def test_probe_script_refuses_to_overwrite_an_existing_run(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "source-audit-001"
            output.mkdir()
            (output / "keep.txt").write_text("keep")
            proc = subprocess.run(
                [sys.executable, str(PROBE), "--root", str(Path(d) / "absent"), "--output", str(output)],
                cwd=REPO,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertEqual((output / "keep.txt").read_text(), "keep")
            self.assertFalse((output / "source_manifest.json").exists())
