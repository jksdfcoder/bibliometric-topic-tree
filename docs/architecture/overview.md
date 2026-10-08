# Architecture

This repository starts with exploration, not a platform claim. The acceptance question is whether a new paper can be placed in a reasonable fine research direction with relevant predecessors and inspectable evidence.

```mermaid
flowchart TD
    A[Existing read-only lake and increments] --> B[Scope candidates and version audit]
    B --> C[Source archive and normalized works]
    C --> D[Lexical / semantic / reference indexes]
    D --> E[Candidate union, reranking and placement evidence]
    E --> F[Topic membership and containment hierarchy]
    E --> G[Time states and independent temporal links]
    F --> H[Search, time layout, semantic zoom and evidence sidebar]
    G --> H
    C -.raw mentions when available.-> I[Independent author pilot]
```

## Boundaries

- `data`: read-only source inventory, version resolution, archival, normalization. Original fields are preserved separately from model features.
- `scope`: text/source/verified-seed candidate recall, human scope decisions; topic entities are not hard boundaries.
- `retrieval` / `encoding`: BM25 and separately versioned scientific/multilingual representations. Inputs start with title/abstract only.
- `relations`: direct references, normalized shared-reference evidence and semantic similarity are distinct. Incoming citations derive by reversing reference edges, with coverage disclosed.
- `positioning`: union recall, independently inspectable ranking, topic support and refusal. The initial baseline may expose provisional human directions before automatic topics exist.
- `topics`: fine groups, membership and explicitly nested containment; does not declare historical splits.
- `temporal`: time states and evidence-backed links; no inferred evolution from a cluster dendrogram.
- `views`: stable publication-time radii, containment/time aggregation, counts and selected cross-links. G6 is a candidate renderer pending audit, not a graph engine to build from scratch.
- `evaluation` / `incremental`: independent labels, leakage isolation, reproducibility, version alignment and stability.

`apps/api` is a thin local service over reviewed artifacts; `apps/web` renders them. Framework and index dependencies are pinned only after P02 audit. Prefer mature components and existing patterns; do not simultaneously fork multiple platforms.

`experiments/bootstrap_20261008` preserves the initial single-partition toolkit and synthetic engineering tests. Formal modules are currently reserved directories. Nothing imports that toolkit as an accepted complete data pipeline.

## Machines and evidence

The lake machine supplies data; Spark supplies conditional compute. Addresses come from local environment. Current memory/clocks/disk are user-reported in `configs/compute/reported_constraints.json`, not measured by this project. CPU BM25 and data audit precede model training. A service stop is not hidden inside data extraction.

## Execution order

Audit source/versions → audit components → normalize tiny real slice → define scope and archive candidates → pilot/independent labels → lexical/scientific/multilingual baselines → citation comparison → new-paper placement → hierarchy/time states → true-data UI → increment stability → evidence-based next-phase decision. Author pilot is conditional and independent.
