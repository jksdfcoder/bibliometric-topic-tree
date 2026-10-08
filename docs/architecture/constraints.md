# Required constraints

1. OpenAlex topics remain reference fields. They do not define corpus hard boundaries, clusters, hierarchy, default training labels or evaluation truth.
2. Author IDs/entities cannot initialize identities, blocks, labels or verified works. Use paper-level raw mentions with provenance; unresolved source IDs stay quarantined. Current reported lake schema lacks raw names/affiliation text, so identity work is conditional.
3. Hierarchy containment, topic time states and temporal links are separate objects and visual semantics. A clustering split is not a historical research split.
4. Reuse the existing lake/increment route. Raw data, formal DB, checkpoints, disambiguation results and old runs stay read-only. Never fabricate missing data or re-crawl a whole corpus because access is missing.
5. First use a real pilot, BM25, SPECTER2 and a reviewed multilingual/general encoder. Train only after stable baseline failures and independently verified examples.
6. Keep source archives broad and model features explicit. Initial representation uses original title/abstract; missing abstract is not novelty. Truncation and token counts must be recorded.
7. Direct citations are not same-problem labels. Normalize shared references; handle review/long-list/common-method bias. Candidate recall is a union, not intersection. Missing evidence differs from score zero.
8. New-paper placement never uses future incoming citations. Retrospective time splits using today's snapshot are named as such, with relation/version/near-duplicate isolation.
9. Uncalibrated scores are not correct probabilities. Allow primary/secondary/multiple associations and refusal/observation.
10. Incoming citations and cited-by counts have coverage and observation time. Reversing a subset of edges is not a complete citation history.
11. Radius is publication time, not topic depth/discovery date. Semantic zoom preserves time spans and deduplicated counts. Root is navigation, not fabricated common origin. Cross-links remain in data.
12. No paid external models, corpus upload, public service, large training, production mutation or service shutdown is implied by implementation tasks.
13. No synthetic/LLM/topic/citation labels can stand in for independent truth. Report diagnostics when labels are absent. Report measurements, failures and uncertainty separately from user reports or README claims.
14. Two Spark devices are not one memory pool. Current resources are constrained and head is reportedly slow; prefer measured single-worker recipes. Do not extrapolate throughput directly from clock ratio or outside benchmarks.
15. Code, model/checkpoint and data permissions are separate. Record exact component commits, actual entry points, license files and revisions before adoption or distribution.
16. Every run records source version, input/config/code/model hashes/revisions, parameters/seeds, resources, paths and completion/failure. Re-run in a fresh directory; downstream consumes completed manifests only.
