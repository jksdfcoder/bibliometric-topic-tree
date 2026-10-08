# Configuration

`data/pilot_scope.json` is an initial candidate-recall/five-year window proposal, not verified core-domain membership. `compute/reported_constraints.json` preserves user-reported resource limits, not measurements.

`data/source.json` is the P01 source-audit policy: no download, no fixed source version, and the manifest filenames the inventory will accept. P03+ add model/input policy, relations/fusion, topics/time windows, view/count and evaluation/split configs according to task contracts. Local access belongs in environment variables, never in tracked files. Save complete resolved config and hash in every run.
