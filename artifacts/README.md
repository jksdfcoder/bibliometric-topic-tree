# Local run artifacts

Use a new `<run_id>/` for every run; previous output/source archives are immutable. Include `manifest.json` and versioned outputs. Downstream reads only completed manifests. Git ignores artifact payloads; put redacted summaries and paths/checksums in `docs/exploration/` or PR evidence instead of committing corpora/models/vectors.

Suggested run contents: source_manifest, raw archive, normalized tables, scope/pilot/split, indexes/embeddings, relations, placement cases, topics/hierarchy/states/links, layout/view, metrics, resources and failure logs. Build only those needed by the assigned task.
