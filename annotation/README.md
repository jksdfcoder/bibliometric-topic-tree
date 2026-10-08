# Independent annotations

Labels are task-specific: corpus scope, same-problem relevance, primary/secondary placement and conditional identity. Preserve reviewer/source, disagreements, unknown states and split/near-duplicate grouping. Human labels require source traceability. LLM output, OpenAlex topics and reference edges are not independent ground truth.

Real annotation payloads stay in the versioned run or `private/` (ignored). This directory holds protocol/templates established by P05; small synthetic fixtures may live in tests with explicit labels as engineering fixtures, not domain truth.
