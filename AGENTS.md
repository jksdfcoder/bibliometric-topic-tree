# Agent instructions

Read `docs/architecture/constraints.md` before changing data, models or evidence. Read `docs/architecture/data_contracts.md` and `interfaces.md` before changing interfaces.

Implementation is assigned by the maintainer. Start an `impl/Pxx-*` branch from current `main`. Read the matching task from `plan:docs/plans/tasks/Pxx-*.md` (or `origin/plan`); its index is `docs/plans/README.md` on that branch. Confirm prerequisite review gates before work. Implement only the assigned slice; do not run other models or sub-agents unless assigned.

Preserve raw sources, formal results and previous runs. Write derived outputs into a fresh `artifacts/<run_id>/`; consumption requires `manifest.status == completed`. Keep credentials, private host addresses, corpora, vectors and model weights out of Git. Use environment variables for access.

OpenAlex topics are reference only. Author IDs/entities are not identity evidence, candidate blocks, labels or verified bibliographies. Resolved IDs in source records remain quarantined. Hierarchy containment and temporal links are different objects.

Real measurements and user-reported facts must have distinct provenance. Synthetic/LLM/OpenAlex-topic/citation labels do not establish accuracy. Reject uncertain placement; uncalibrated scores are not probabilities. Historical splits from today's snapshot are retrospective experiments.

Submit one PR per reviewable task to `main`, using `.github/PULL_REQUEST_TEMPLATE.md`. Include commands, dataset/model/code versions, evidence paths and unresolved limitations. Do not auto-merge or claim downstream stages complete. Existing `experiments/bootstrap_20261008` is historical, not production code to import unchanged.
