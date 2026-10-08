# Reviews

Codex reviews assigned implementation PRs after delivery. Each review accounts for every acceptance criterion in the matching plan task, verifies changed interfaces against architecture contracts, and reads real command results and limitations.

Record `Pxx-review.md`: PR/commit → criteria pass/fail/unverified → concrete findings with file/line → tests/evidence → missing checks → recommendation. Do not confuse engineering fixture success, user reports or README claims with corpus/model performance.

A task can be blocked or limited with an explicit gate decision. A downstream model may not remove an unresolved gate by inventing a source, label, trained checkpoint or metric.
