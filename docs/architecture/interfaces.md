# Formal interfaces v1 (implementation targets)

All records follow `data_contracts.md`. Paths refer to fresh artifact directories. The pipeline does not exist yet; task PRs implement these signatures or propose an explicit contract revision.

```python
# data/inventory.py — P01
inspect_source(root: Path, output: Path) -> dict
# data/normalize.py and source.py — P03
normalize_work(raw: dict, source_version: str, policy: dict) -> dict
iter_latest_works(root: Path, source_manifest: dict) -> Iterator[dict]
load_reference_sets(root: Path, work_ids: set[str], source_manifest: dict) -> dict[str, dict]
# data/archive.py — P03/P04
archive_selected(root: Path, work_ids: set[str], source_manifest: dict, output: Path) -> dict
# scope/recall.py — P04
recall_candidates(works: Iterable[dict], config: dict, source_manifest: dict) -> Iterator[dict]
# evaluation/pilot.py and labels.py — P05
build_pilot(works: Iterable[dict], scope: Iterable[dict], config: dict) -> list[dict]
validate_labels(labels: list[dict], split_config: dict) -> dict
# retrieval/bm25.py — P06
build_bm25(works: Iterable[dict], config: dict, output: Path) -> dict
search_bm25(index: Path, query: str, limit: int) -> list[dict]
# encoding/encode.py — P07
encode_works(works: Iterable[dict], model_spec: dict, output: Path) -> dict
encode_query(query: str, model_spec: dict) -> dict
# retrieval/semantic.py — P07
search_semantic(index: Path, query_vector: list[float], limit: int) -> list[dict]
# relations/references.py and fusion.py — P08
shared_reference_candidates(work_id: str, reference_index: Path, config: dict) -> list[dict]
fuse_candidates(channels: dict[str, list[dict]], config: dict) -> list[dict]
# positioning/place.py — P09
place_work(work: dict, indexes: dict, topic_support: dict | None, config: dict) -> dict
# topics/build.py and hierarchy.py — P10
build_topics(works: Iterable[dict], neighbor_graph: Path, config: dict, output: Path) -> dict
build_hierarchy(topics: list[dict], memberships: list[dict], config: dict) -> dict
# temporal/states.py and links.py — P11
build_states(works: list[dict], memberships: list[dict], windows: list[dict]) -> list[dict]
link_states(states: list[dict], evidence: dict, config: dict) -> list[dict]
# views/export.py — P12
export_view(hierarchy: dict, states: list[dict], links: list[dict], config: dict, output: Path) -> dict
# incremental/apply.py — P13
apply_increment(run: Path, new_records: Iterable[dict], source_manifest: dict, config: dict, output: Path) -> dict
# evaluation/metrics.py — P05/P06/P08
ndcg_at_k(ranked_work_ids: list[str], relevance: dict[str, int], k: int = 10) -> float | None
```

Retrieved rows: `work_id`, `rank`, `raw_score`, `channel`, `evidence`, `missing_state`, `method_version`. Rankings are finite and deterministic under the same run/config; tie rules use work ID. Evidence IDs remain resolvable in the source artifact.

`place_work` returns `schemas/placement.schema.json`: unavailable topic support gives explicit provisional/no-topic state rather than invented hierarchy. It can return observation/refusal with lexical/text/reference evidence. Final topic-backed placement is completed after P10 and reused in P12/P13; P09 itself does not require already-implemented automatic topics.

`archive_selected` includes a main/side-table inventory and outgoing/incoming coverage. It does not launch API collection, stop services, fetch author entities or download PDFs.

## Planned CLI

P03 establishes `python -m atlas inspect/normalize`, run manifest utilities and dispatcher. P04 adds `extract`; P05 `pilot/annotation-check/evaluate`; P06 `index/search`; P07 `encode`; P08 `relations`; P09 `place`; P10 `topics`; P11 `temporal`; P12 `export-view`; P13 `increment/run`. Commands listed in task plans are proposed acceptance interfaces, not current runnable commands.

## Planned local API

P12 implements read-only `/health`, `/search`, `/works/{id}/evidence`, `/topics/{id}`, `/view?level=...&window=...`, `/placements/{id}`. It reads reviewed artifacts and exposes methods/missingness/version. Bind loopback by default. No public deployment, auth/billing platform or collection endpoint in this phase.
