# Historical extraction sandbox (2026-10-08)

Transferred from the local Research Atlas exploration. Contains read-only source/schema probes, a native-work extractor and a single-update-partition pilot with optional wide side-table archival and partial incoming references. Tests use synthetic records; 12 engineering tests passed in the source workspace.

Limits: single partition is not full five-year corpus; keywords are unverified scope candidates; side-table date equality does not establish complete current reference-set semantics; source-only author IDs are quarantined; raw author fields are absent in the user-reported lake; model baselines, topic tree and UI are not implemented. Do not import these scripts as formal modules without P01/P03 review. No raw corpus, models, labels or credentials are transferred.

```sh
python3 -m unittest discover -s experiments/bootstrap_20261008/tests -v
```
