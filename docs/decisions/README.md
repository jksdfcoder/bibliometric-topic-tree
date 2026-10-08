# Architecture decisions

Record an ADR before adopting a source join rule, retrieval component, model/checkpoint, renderer, training recipe or changed contract. Include the actual evidence, alternatives, exact commit/entry point/license, integration scope and validation. README capability claims alone do not establish reuse.

P02 audits SPECTER2, BERTopic, BERTrend, G6 and optionally litdb; use only needed components. S2AND/Disamb/Jev review belongs to conditional P14. bm25s, Faiss, Vue, Nuxt, and G6 have a verified adopt decision from a local license and load check. Checkpoints remain unverified and are not redistributed.

Template: problem → evidence/provenance → alternatives → chosen scope → exact version/license/entry point → minimal changes → checks/failures → revisit trigger. Store as `ADR-XXXX-description.md`.
