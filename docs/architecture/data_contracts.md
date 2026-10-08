# Data contracts v1 (planned formal pipeline)

Use Parquet plus lightweight local indexing/DuckDB where audited and useful. Source archives preserve raw columns; JSONL is acceptable for small evidence/export artifacts. These contracts are implementation targets, not existing tables.

## Identifiers and provenance

`work_id` is an internal string assigned deterministically from source namespace plus source ID. An OpenAlex work ID is a source work identifier, never an author identity. `source_ids` retains namespace and original ID. A normalization revision changing IDs requires a mapping artifact. Group DOI/preprint/near-duplicates explicitly; do not merge source records silently.

`source_version` identifies a frozen source manifest. `source_updated_at` preserves the most precise source timestamp; `source_created_date` remains distinct from `first_discovered_at`. Historical first discovery is null without logs. `raw_record_hash` hashes canonical raw content; `input_hash` hashes only the versioned model text. UTC timestamps use ISO8601; dates are YYYY-MM-DD. Missing values are null plus diagnostic state.

## Records

| Object | Required fields | Meaning |
|---|---|---|
| works | work_id, source_ids, title, abstract, abstract_status, publication_date, first_discovered_at, source_created_date, source_updated_at, source_version, raw_record_hash, input_hash, type, doi, authorships_truncated | Text/time/provenance; extras remain archived |
| references | citing_work_id, cited_work_id, source_version, source_updated_at, provenance, reference_set_version | Directed citing→cited; out-of-scope endpoints allowed |
| incoming citation view | target_work_id, citing_work_id, source_version, observation_time, coverage | Derived from directed edges; no completeness claim from a partial scan |
| scope membership | work_id, scope_class, recall_evidence, decision_source, decision_version, reviewer, status | core/adjacent/applied/excluded/unknown; recall candidates differ from decisions |
| embeddings | work_id, model_revision, adapter_revision, tokenizer_revision, input_hash, input_policy_version, token_count, truncated_tokens, missing_state, dimension, vector | Only reviewed input fields enter model |
| relations | left_work_id, right_work_id, evidence_type, raw_score, normalization, evidence_ids, missing_state, method_version, source_version | Independent semantic/shared-reference/direct-reference evidence |
| topic membership | work_id, topic_id, role, strength, method_version, correction_version | role primary/secondary; strength uncalibrated unless validated |
| topic | topic_id, label, label_status, representative_work_ids, distinguishing_terms, evidence_spans, method_version | Names supported by text/representatives, not generated truth |
| hierarchy edge | parent_topic_id, child_topic_id, hierarchy_version, containment_evidence | Nested containment, not temporal ancestry |
| topic state | state_id, topic_id, window_start, window_end, member_work_ids, unique_work_count, coverage, summary_evidence, method_version | Defined publication window and observed contents |
| temporal link | from_state_id, to_state_id, link_type, evidence, missing_state, method_version, status | evidence-backed association; candidate/verified/unknown, not automatic historical split |
| layout | node_id, source_object_id, radius_time, angle_group, count_window, unique_count, represented_start/end, layout_version, previous_node_id | Time and aggregation are explicit |
| raw mention | mention_id, work_id, raw_name, raw_affiliation_strings, byline_index, source_version, provenance | Content/order changes create a new version/mention; raw-only |
| person attribution | mention_id, person_id, status, evidence, attribution_version, prior_version | Independent conditional author pilot; reversible |

## Field states and archives

- abstract: `present`, `missing`, `position_gaps`, `malformed`; malformed input must fail or be quarantined with reason. Arrow map converts key/value pairs while preserving positions and detecting duplicate positions/keys. No silent long-text loss.
- reference set: `present`, `reported_empty`, `unknown_no_rows`, `version_conflict`, `partial`. Side-table absence is not reported_empty. P01 determines side-table snapshot/revision semantics before P03 normalizes sets.
- model scores: raw, normalized/rank-fused and missing flags remain separate. A refusal cannot be explained as novelty solely from missing abstract/reference.
- raw work/side tables: preserve all retrievable columns with per-record/table provenance. All-selected-work outgoing and all-lake matching incoming references are different scans with different coverage manifests.
- unresolved `author_id` and resolved profiles are quarantined source artifacts only; formal raw mention and person objects never fall back to entity fields. Source topics/concepts/keywords are archival/reference-only for baseline v1.

## Topic counting

`unique_work_count` is the union of work IDs in a window; multiple membership must not double count a parent/domain total. Child totals can exceed parent unique total if memberships overlap; expose that rule, do not silently sum children. A topic state and hierarchy parent span use defined publication windows. Undated works belong to an explicit unknown-time bucket, not today's outer ring.

## Time evaluation and incremental changes

Partition/update dates do not constrain publication windows unless source semantics prove it safe. Five-year target corpus and older/out-of-domain predecessor context are separate collections. Snapshot-based historical evaluation is retrospective; use available index snapshots for true as-of claims. Incoming citations after query time are barred from features. Group versions/near-duplicates before split assignment.

## Output schemas

`schemas/run_manifest.schema.json` and `schemas/placement.schema.json` fix the baseline outer interface. Task-specific files follow this document and are added in their implementation PR. Schema validation alone is not a semantic or model-quality test.
