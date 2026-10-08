# Scripts

Reserved for read-only source probes, contract checks and rerun wrappers in the assigned task PRs. Historical probes are in experiments/bootstrap_20261008. No script automatically collects a full corpus, mutates production or stops inference services.

P01 entry: `python3 scripts/probe_source.py --root /opt/openalex --output artifacts/source-audit-001`. A missing or unreadable root is recorded as blocked. An existing output directory is left untouched.
