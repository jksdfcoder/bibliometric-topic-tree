# Implementation and review

The maintainer assigns a task and model. `plan` holds task specifications; implementation branches start from `main`, not from an entire unreviewed implementation branch. A dependency passes only when its interface/evidence has been reviewed, not when another agent says it is done.

1. Read the assigned task and central architecture/contracts. Check current `main` for prerequisite interfaces.
2. Create `impl/Pxx-description`; preserve unrelated files and existing source data.
3. Implement the smallest task slice; update contract changes explicitly in the PR.
4. Run the task's meaningful unit/integration tests and permitted real diagnostic. Record skipped checks with reasons.
5. Open a PR to `main` with versioned evidence and limitations. Codex reviews against the task and contracts; maintainer controls merge.

The `plan` branch is an instruction snapshot, not a branch to merge wholesale. Accepted architecture/contract changes belong to `main`; update future task specs to match them deliberately.

No corpus, credentials, model weights or vectors belong in commits. Small synthetic fixtures are allowed and clearly labelled. Human annotations or copyrighted source excerpts require provenance/privacy review before publication; use artifact references instead of uploading a corpus.

Review records go into `docs/reviews/Pxx-review.md`; decisions into `docs/decisions/ADR-XXXX.md`; measured results/failures into `docs/exploration/`. Do not overwrite older run evidence or frozen thresholds.
