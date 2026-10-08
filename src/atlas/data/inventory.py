"""Read-only source inventory. Never downloads a corpus."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

try:
    import pyarrow.parquet as pq
except ImportError:  # pragma: no cover - optional reader
    pq = None

# ponytail: value samples stop at sample_rows_per_file (default 32). A larger
# file cannot prove reference-set semantics. Upgrade path: a full id-keyed pass
# after an approved join rule.
SAMPLE_DEFAULT = 32
MANIFEST_NAMES = (
    "snapshot_manifest.json",
    "conversion_manifest.json",
    "source_snapshot.json",
)
ALWAYS_TABLES = (
    "works",
    "works_referenced_works",
    "works_authorships",
    "works_authorships_affiliations",
    "works_authorships_institutions",
    "sources",
)
FIELD_SPECS = (
    ("work_id", "works", ("id", "work_id")),
    ("title", "works", ("title", "display_name")),
    ("abstract", "works", ("abstract", "abstract_inverted_index")),
    ("publication_date", "works", ("publication_date",)),
    ("source_created_date", "works", ("created_date",)),
    ("source_updated_at", "works", ("updated",)),
    ("source_updated_date", "works", ("updated_date",)),
    ("type", "works", ("type",)),
    ("doi", "works", ("doi",)),
    ("referenced_work_id", "works_referenced_works", ("referenced_work_id",)),
    ("raw_name", "works_authorships", ("raw_author_name", "raw_name")),
    ("author_position", "works_authorships", ("author_position",)),
    ("raw_affiliation", "works_authorships_affiliations", ("raw_affiliation_strings", "raw_affiliation")),
    ("source_id", "works", ("source_id",)),
    ("source_name", "sources", ("display_name",)),
)
VERSION_ROLES = {"update", "full_base", "historical_multi_version"}
SEMANTIC_KEYS = ("reference_set_semantics", "deletion_semantics", "empty_side_table_semantics")
STAT_COLUMNS = ("publication_date", "updated", "updated_date", "created_date")
MODULE_NAMES = ("pyarrow", "duckdb", "torch", "sentence_transformers")
NULL_INVENTORY = {
    "measured": False,
    "tables": None,
    "schema_samples": None,
    "coverage": None,
    "rows": None,
    "source_version": None,
}


def inspect_source(root: Path, output: Path) -> dict:
    root = Path(root)
    output = Path(output)
    if not root.exists():
        raise FileNotFoundError(f"Input unavailable: {root}. No fallback download is performed.")
    if not root.is_dir():
        raise NotADirectoryError(f"Lake root is not a directory: {root}")
    root_resolved = root.resolve()
    output_resolved = output.resolve()
    if output_resolved == root_resolved or root_resolved in output_resolved.parents:
        raise ValueError("Output must be outside the read-only source tree")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing run: {output}")
    config = _load_config()
    result = _build(root, _sample_cap(config))
    output.mkdir(parents=True)
    _write_json(output / "inventory.json", result)
    _write_manifest(output, result, config, error=None)
    return result


def write_access_failure(output: Path, exc: BaseException) -> dict:
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing run: {output}")
    output.mkdir(parents=True)
    _write_json(output / "inventory.json", NULL_INVENTORY)
    missing = [
        "readable_lake_root",
        "snapshot_or_conversion_manifest",
        "reference_set_semantics",
        "deletion_semantics",
        "empty_side_table_semantics",
    ]
    limitations = _limitations("blocked")
    config = _load_config()
    manifest = _write_manifest(
        output,
        {
            "status": "blocked",
            "source_version": None,
            "source_version_fixed": False,
            "normalized_references_allowed": False,
            "missing_inputs": missing,
            "limitations": limitations,
            "runtime": _runtime(),
        },
        config,
        error=f"{type(exc).__name__}: {exc}",
    )
    return {
        "status": "blocked",
        "source_version": None,
        "normalized_references_allowed": False,
        "inventory": dict(NULL_INVENTORY),
        "manifest": manifest,
    }


def write_environment(output: Path) -> dict:
    payload = measure_local_environment()
    _write_json(Path(output) / "environment.json", payload)
    return payload


def measure_local_environment() -> dict:
    env = _runtime()
    env["host_role"] = "local_audit_process"
    env["gpu"] = _gpu_probe()
    env["vllm_process_seen_on_audit_host"] = _vllm_seen()
    return env


def _build(root: Path, sample_cap: int) -> dict:
    directories = {path.name: path for path in root.iterdir() if path.is_dir()}
    names = list(ALWAYS_TABLES)
    names.extend(sorted(name for name in directories if name not in ALWAYS_TABLES))
    tables = {}
    work_rows = []
    ref_rows = []
    for name in names:
        role = _role(name)
        sample_kind = None
        if name == "works":
            sample_kind = "works"
        elif name == "works_referenced_works":
            sample_kind = "references"
        table, samples = _inventory_directory(directories.get(name), role, sample_kind, sample_cap)
        tables[name] = table
        if sample_kind == "works":
            work_rows = samples
        elif sample_kind == "references":
            ref_rows = samples
    join = _join_samples(work_rows, ref_rows)
    _set_sample_complete(tables, join)
    manifests = _load_manifests(root)
    decision = _decide(tables, join, manifests)
    fields = _fields(tables, decision["source_version"] if decision["source_version_fixed"] else None)
    column_names = _column_names(tables)
    return {
        "measured": True,
        "status": decision["status"],
        "source_version": decision["source_version"],
        "source_version_fixed": decision["source_version_fixed"],
        "source_version_candidates": decision["candidates"],
        "partition_role": decision["partition_role"],
        "partition_role_basis": decision["partition_role_basis"],
        "normalized_references_allowed": decision["normalized_references_allowed"],
        "missing_inputs": decision["missing_inputs"],
        "unverified": list(decision["missing_inputs"]),
        "limitations": _limitations(decision["status"]),
        "coverage": {
            "publication_date": None,
            "abstract": None,
            "references": None,
            "raw_name": None,
            "raw_affiliation": None,
        },
        "tables": tables,
        "fields": fields,
        "reference_join": join,
        "raw_mentions": {
            "raw_name_observed": "raw_author_name" in column_names["works_authorships"] or "raw_name" in column_names["works_authorships"],
            "raw_affiliation_observed": bool(
                {"raw_affiliation_strings", "raw_affiliation"} & column_names["works_authorships_affiliations"]
            ),
            "filled_from_author_entity": False,
        },
        "author_entity_tables": sorted(name for name, table in tables.items() if table["role"] == "author_entity" and table["present"]),
        "author_entity_values_read": any(
            table["value_rows_read"] > 0 for table in tables.values() if table["role"] == "author_entity"
        ),
        "source_dimension_readable": _source_readable(tables.get("sources")),
        "source_ids_resolved_to_names": False,
        "runtime": _runtime(),
        "error": None,
    }


def _decide(tables: dict, join: dict, manifests: list) -> dict:
    missing = []
    usable = [item for item in manifests if item["doc"] is not None]
    version = None
    role = None
    if not manifests:
        missing.append("snapshot_or_conversion_manifest")
    elif len(manifests) != 1 or len(usable) != 1:
        missing.append("unique_snapshot_manifest")
    else:
        doc = usable[0]["doc"]
        raw_version = doc.get("source_version")
        if isinstance(raw_version, str) and raw_version.strip():
            version = raw_version.strip()
        else:
            missing.append("snapshot_or_conversion_manifest")
        raw_role = doc.get("partition_role")
        if raw_role in VERSION_ROLES:
            role = raw_role
        else:
            missing.append("partition_role")
        for key in SEMANTIC_KEYS:
            value = doc.get(key)
            if not isinstance(value, str) or not value.strip():
                missing.append(key)
    works = tables["works"]
    refs = tables["works_referenced_works"]
    if not works["present"] or not works["file_count"] or works["rows"] is None or works["errors"]:
        missing.append("works_table")
    if not refs["present"]:
        missing.append("reference_side_table")
    if _pyarrow_missing(tables):
        missing.append("pyarrow_unavailable")
    elif _any_errors(tables):
        missing.append("unreadable_parquet")
    conflicts = any((
        join["different_timestamp"],
        join["different_date_diagnostic"],
        join["precision_mismatch"],
        join["cross_partition_conflicts"],
    ))
    if not join["sample_complete"]:
        missing.append("reference_sample_incomplete")
    if conflicts:
        missing.append("reference_version_conflict")
    if join["duplicate_ids_same_partition"]:
        missing.append("duplicate_work_ids")
    if join["sample_complete"] and not conflicts and join["no_side_rows"]:
        missing.append("reference_side_rows_unknown")
    timestamps_prove = (
        join["sample_complete"]
        and not conflicts
        and join["duplicate_ids_same_partition"] == 0
        and join["no_side_rows"] == 0
        and join["work_occurrences"] > 0
        and join["same_timestamp"] == join["work_occurrences"]
    )
    if join["sample_complete"] and not conflicts and not join["no_side_rows"] and not timestamps_prove:
        missing.append("reference_version_unproven")
    fixed = not missing
    if conflicts or join["duplicate_ids_same_partition"]:
        state = "version_conflict"
    elif not refs["present"] or refs["rows"] == 0 or (
        join["no_side_rows"] and join["same_timestamp"] == 0 and join["same_date_diagnostic"] == 0
    ):
        state = "unknown_no_rows"
    elif fixed:
        state = "consistent_timestamp"
    else:
        state = "unproven"
    join["state"] = state
    candidates = [
        {"value": label, "kind": "partition_directory", "selected": False}
        for label in works["partitions"]
    ]
    if version:
        candidates.append({"value": version, "kind": "snapshot_manifest", "selected": fixed})
    return {
        "status": "completed" if fixed else "blocked",
        "source_version": version if fixed else None,
        "source_version_fixed": fixed,
        "normalized_references_allowed": fixed,
        "partition_role": role if fixed and role else "unknown",
        "partition_role_basis": "snapshot_manifest" if fixed and role else "unverified",
        "missing_inputs": missing,
        "candidates": candidates,
    }


def _join_samples(work_rows: list, ref_rows: list) -> dict:
    counts = {
        "same_timestamp": 0,
        "different_timestamp": 0,
        "same_date_diagnostic": 0,
        "different_date_diagnostic": 0,
        "precision_mismatch": 0,
        "no_side_rows": 0,
        "cross_partition_conflicts": 0,
        "duplicate_ids_same_partition": 0,
        "work_occurrences": len(work_rows),
        "sample_complete": False,
    }
    refs = defaultdict(list)
    for row in ref_rows:
        refs[row["id"]].append(row["token"])
    for row in work_rows:
        kind = _classify_refs(row["token"], refs.get(row["id"], []))
        counts[kind] += 1
    by_id = defaultdict(list)
    for row in work_rows:
        by_id[row["id"]].append(row)
    for rows in by_id.values():
        partitions = {row["partition"] for row in rows}
        if len(partitions) >= 2:
            tokens = {row["token"] for row in rows}
            if len(tokens) == 1 and _is_timestamp(next(iter(tokens))):
                pass
            elif any(not _is_timestamp(token) for token in tokens):
                counts["precision_mismatch"] += 1
            else:
                counts["cross_partition_conflicts"] += 1
        by_partition = defaultdict(list)
        for row in rows:
            by_partition[row["partition"]].append(row)
        for group in by_partition.values():
            if len(group) > 1:
                counts["duplicate_ids_same_partition"] += 1
    return counts


def _classify_refs(work_token, ref_tokens) -> str:
    if not ref_tokens:
        return "no_side_rows"
    kind_mismatch = False
    values_differ = False
    matched_kind = None
    for ref_token in ref_tokens:
        if not _is_timestamp(work_token) and not _is_date(work_token):
            kind_mismatch = True
            continue
        if ref_token is None or work_token is None or ref_token[0] != work_token[0]:
            kind_mismatch = True
            continue
        if ref_token != work_token:
            values_differ = True
        else:
            matched_kind = work_token[0]
    if kind_mismatch:
        return "precision_mismatch"
    if values_differ and work_token and work_token[0] == "timestamp":
        return "different_timestamp"
    if values_differ:
        return "different_date_diagnostic"
    if matched_kind == "timestamp":
        return "same_timestamp"
    if matched_kind == "date":
        return "same_date_diagnostic"
    return "precision_mismatch"


def _inventory_directory(directory: Path | None, role: str, sample_kind: str | None, sample_cap: int):
    empty = _empty_table(role)
    if directory is None:
        return empty, []
    files = sorted(path for path in directory.rglob("*.parquet") if path.is_file())
    records = []
    samples = []
    complete = True
    if not files:
        complete = sample_kind is None
    for path in files:
        record, file_samples, file_complete = _read_parquet(path, directory, sample_kind, sample_cap)
        records.append(record)
        samples.extend(file_samples)
        complete = complete and file_complete
    rows = None
    row_groups = None
    if records and all(item["error"] is None and item["rows"] is not None for item in records):
        rows = sum(item["rows"] for item in records)
        row_groups = sum(item["row_groups"] for item in records)
    groups = _schema_groups(records)
    table = {
        "present": True,
        "role": role,
        "files": [_public_file(item) for item in records],
        "file_count": len(records),
        "bytes": sum(item["bytes"] for item in records),
        "rows": rows,
        "row_groups": row_groups,
        "partitions": _partitions(records),
        "schema_groups": groups,
        "schema_differs": len(groups) > 1,
        "column_statistics_present": _aggregate_stats(records),
        "value_rows_read": sum(item["sample_rows_read"] for item in records) if sample_kind else 0,
        "errors": any(item["error"] for item in records),
        "sample_complete": complete and not any(item["error"] for item in records),
    }
    if sample_kind is None:
        samples = []
    return table, samples


def _read_parquet(path: Path, table_root: Path, sample_kind: str | None, sample_cap: int):
    relative = path.relative_to(table_root).as_posix()
    record = {
        "path": relative,
        "bytes": path.stat().st_size,
        "rows": None,
        "row_groups": None,
        "columns": [],
        "error": None,
        "statistics_present": {},
        "sample_rows_read": 0,
        "identity_readable": False,
    }
    if pq is None:
        record["error"] = "pyarrow_unavailable"
        return record, [], False
    try:
        parquet = pq.ParquetFile(path)
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record, [], False
    metadata = parquet.metadata
    record["rows"] = metadata.num_rows
    record["row_groups"] = metadata.num_row_groups
    record["columns"] = [{"name": field.name, "type": str(field.type)} for field in parquet.schema_arrow]
    names = [column["name"] for column in record["columns"]]
    record["statistics_present"] = _stats_present(parquet, names)
    record["identity_readable"] = "id" in names or "work_id" in names
    if sample_kind is None:
        return record, [], True
    if not record["identity_readable"]:
        return record, [], record["rows"] == 0
    columns = [name for name in ("id", "work_id", "updated", "updated_date") if name in names]
    raw_rows = []
    try:
        for batch in parquet.iter_batches(batch_size=sample_cap, columns=columns):
            for row in batch.to_pylist():
                if len(raw_rows) >= sample_cap:
                    break
                raw_rows.append(row)
            if len(raw_rows) >= sample_cap:
                break
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        return record, [], False
    record["sample_rows_read"] = len(raw_rows)
    partition = _partition_label(relative)
    samples = []
    for row in raw_rows:
        identity = _identity(row)
        if identity is None:
            continue
        samples.append({"id": identity, "token": _token(row), "partition": partition})
    complete = record["rows"] is not None and record["rows"] <= len(raw_rows)
    return record, samples, complete


def _stats_present(parquet, names: list) -> dict:
    wanted = [name for name in STAT_COLUMNS if name in names]
    flags = {name: False for name in wanted}
    metadata = parquet.metadata
    if metadata is None or metadata.num_row_groups == 0:
        return flags
    indexes = {name: parquet.schema_arrow.get_field_index(name) for name in wanted}
    seen = {name: 0 for name in wanted}
    good = {name: 0 for name in wanted}
    for group_index in range(metadata.num_row_groups):
        group = metadata.row_group(group_index)
        for name, index in indexes.items():
            if index < 0:
                continue
            seen[name] += 1
            try:
                stats = group.column(index).statistics
            except Exception:
                stats = None
            if stats is not None and getattr(stats, "has_min_max", False):
                good[name] += 1
    return {name: seen[name] > 0 and good[name] == seen[name] for name in wanted}


def _public_file(record: dict) -> dict:
    return {
        "path": record["path"],
        "bytes": record["bytes"],
        "rows": record["rows"],
        "row_groups": record["row_groups"],
        "columns": record["columns"],
        "error": record["error"],
        "statistics_present": record["statistics_present"],
    }


def _schema_groups(records: list) -> list:
    grouped = defaultdict(list)
    for record in records:
        if record["error"] or not record["columns"]:
            continue
        signature = tuple(sorted((column["name"], column["type"]) for column in record["columns"]))
        grouped[signature].append(record["path"])
    groups = []
    for signature in sorted(grouped):
        groups.append({
            "columns": [{"name": name, "type": kind} for name, kind in signature],
            "files": sorted(grouped[signature]),
        })
    return groups


def _aggregate_stats(records: list) -> dict:
    flags = {}
    readable = [record for record in records if record["error"] is None]
    for name in STAT_COLUMNS:
        holders = [record for record in readable if any(column["name"] == name for column in record["columns"])]
        flags[name] = bool(holders) and all(record["statistics_present"].get(name) for record in holders)
    return flags


def _partitions(records: list) -> list:
    labels = {_partition_label(record["path"]) for record in records if record["error"] is None}
    labels.discard("")
    return sorted(labels)


def _partition_label(relative: str) -> str:
    parent = str(Path(relative).parent)
    return "" if parent == "." else parent


def _empty_table(role: str) -> dict:
    return {
        "present": False,
        "role": role,
        "files": [],
        "file_count": None,
        "bytes": None,
        "rows": None,
        "row_groups": None,
        "partitions": [],
        "schema_groups": [],
        "schema_differs": False,
        "column_statistics_present": {name: False for name in STAT_COLUMNS},
        "value_rows_read": 0,
        "errors": False,
        "sample_complete": False,
    }


def _fields(tables: dict, source_version: str | None) -> list:
    fields = []
    basis = source_version or "unverified"
    for field, table_name, candidates in FIELD_SPECS:
        observed_names = _column_names(tables)[table_name]
        table = tables.get(table_name)
        fields.append({
            "field": field,
            "table": table_name,
            "candidate_columns": list(candidates),
            "observed_columns": [name for name in candidates if name in observed_names],
            "table_present": bool(table and table["present"]),
            "version_basis": basis,
        })
    return fields


def _column_names(tables: dict) -> dict:
    names = defaultdict(set)
    for table_name, table in tables.items():
        for record in table["files"]:
            for column in record["columns"]:
                names[table_name].add(column["name"])
    for field, table_name, _candidates in FIELD_SPECS:
        names.setdefault(table_name, set())
    return names


def _load_manifests(root: Path) -> list:
    found = []
    for name in MANIFEST_NAMES:
        path = root / name
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            found.append({"name": name, "doc": None, "error": str(exc)})
            continue
        if not isinstance(doc, dict):
            found.append({"name": name, "doc": None, "error": "manifest is not an object"})
            continue
        found.append({"name": name, "doc": doc, "error": None})
    return found


def _source_readable(table: dict | None) -> bool:
    if not table or not table["present"] or table["errors"]:
        return False
    return any(record["columns"] and record["error"] is None for record in table["files"])


def _pyarrow_missing(tables: dict) -> bool:
    return any(
        record["error"] == "pyarrow_unavailable"
        for table in tables.values()
        for record in table["files"]
    )


def _any_errors(tables: dict) -> bool:
    return any(table["errors"] for table in tables.values())


def _role(name: str) -> str:
    if name == "works" or name.startswith("works_"):
        return "works"
    if name == "authors" or name.startswith("authors_"):
        return "author_entity"
    if name == "sources" or name.startswith("sources_"):
        return "source_dimension"
    return "other"


def _limitations(status: str) -> list:
    items = [
        "coverage_not_measured",
        "author_entities_not_used",
        "directory_dates_are_not_snapshot_dates",
        "no_service_shutdown",
        "absence_is_not_reported_empty",
        "deletion_counts_not_independently_counted",
    ]
    if status == "completed":
        items.insert(1, "audit_complete_does_not_mean_coverage_complete")
    return items


def _identity(row: dict):
    value = row.get("id")
    if value is None:
        value = row.get("work_id")
    if value is None or isinstance(value, bool):
        return None
    return str(value)


def _token(row: dict):
    updated = row.get("updated")
    if updated is not None:
        return ("timestamp", _iso(updated))
    updated_date = row.get("updated_date")
    if updated_date is not None:
        return ("date", _iso(updated_date))
    return None


def _iso(value) -> str:
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        else:
            value = value.astimezone(dt.timezone.utc)
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


def _is_timestamp(token) -> bool:
    return bool(token) and token[0] == "timestamp"


def _is_date(token) -> bool:
    return bool(token) and token[0] == "date"


def _runtime() -> dict:
    return {
        "evidence_class": "measured_local_process",
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "spark_confirmed": False,
        "lake_host_role": "unverified",
        "step_time_seconds": None,
        "clock_ratio_used_as_step_time": False,
        "service_shutdown": False,
        "modules": {name: _importable(name) for name in MODULE_NAMES},
    }


def _gpu_probe() -> dict:
    if shutil.which("nvidia-smi") is None:
        return {"nvidia_smi": "unavailable"}
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"nvidia_smi": "error", "error": str(exc)}
    return {"nvidia_smi": "ran", "exit_code": proc.returncode, "summary": proc.stdout.strip()[:500]}


def _vllm_seen():
    try:
        proc = subprocess.run(
            ["ps", "-ax", "-o", "comm="],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return any("vllm" in line.lower() for line in proc.stdout.splitlines())


def _importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ValueError:
        return False


def _load_config() -> dict:
    path = _repo_root() / "configs" / "data" / "source.json"
    if path.is_file():
        raw = path.read_bytes()
        return {"hash": hashlib.sha256(raw).hexdigest(), "resolved": json.loads(raw)}
    resolved = {
        "download_on_missing": False,
        "sample_rows_per_file": SAMPLE_DEFAULT,
        "source_version": None,
        "recognized_manifest_filenames": list(MANIFEST_NAMES),
    }
    return {"hash": _digest(resolved), "resolved": resolved}


def _sample_cap(config: dict) -> int:
    value = config["resolved"].get("sample_rows_per_file", SAMPLE_DEFAULT)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return SAMPLE_DEFAULT
    return value


def _write_manifest(output: Path, result: dict, config: dict, error: str | None) -> dict:
    inventory_hash = hashlib.sha256((output / "inventory.json").read_bytes()).hexdigest()
    manifest = {
        "run_id": output.name,
        "status": result["status"],
        "stage": "source_audit",
        "code": {"commit": _git_head(), "content_hash": _content_hash()},
        "data": {
            "source_version": result["source_version"] if result["source_version_fixed"] else "unverified",
            "source_version_fixed": result["source_version_fixed"],
            "input_manifest_hash": inventory_hash,
            "input_manifest_hash_basis": "inventory_file",
        },
        "config": config,
        "models": [],
        "resources": result["runtime"],
        "outputs": [{"path": "inventory.json", "hash": inventory_hash}],
        "limitations": result["limitations"],
        "error": error,
        "missing_inputs": result["missing_inputs"],
        "normalized_references_allowed": result["normalized_references_allowed"],
    }
    _write_json(output / "source_manifest.json", manifest)
    return manifest


def _git_head():
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _content_hash() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _digest(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _set_sample_complete(tables: dict, join: dict) -> None:
    works = tables["works"]
    refs = tables["works_referenced_works"]
    join["sample_complete"] = bool(
        works["present"]
        and refs["present"]
        and works.get("sample_complete")
        and refs.get("sample_complete")
        and not works["errors"]
        and not refs["errors"]
    )
