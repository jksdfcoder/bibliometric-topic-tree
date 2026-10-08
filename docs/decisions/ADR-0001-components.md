# ADR-0001: Components, checkpoints, and licenses

Status: minimal pin accepted. Checkpoints stay candidates. This ADR does not set a project license.

Date: 2026-10-08.

Audit machine: Apple M4 Max, arm64, macOS 26.5.2, 64 GB RAM, Python 3.9.6, Node v24.15.0. Spark was not contacted. The user-reported Spark memory, clocks, and `vllm-fn` occupancy were not remeasured, and no service was stopped. No public service was started. No encoder weights were downloaded.

Evidence inventory: `docs/decisions/component_inventory.json`. Model specs: `configs/models/candidate_models.json`.

## Problem

The pipeline needs a lexical index, an exact vector index, a scientific encoder, one multilingual encoder, topic representation/hierarchy modules, a temporal-link model, and a UI shell with a graph view. Each adopted item needs a fixed commit, a source entry point, a license file read from that commit, and a load probe on this machine. A README license line is not a license file. An unknown weight license is not Apache or MIT, and those checkpoints are not distributed.

## Adopted pin

| Component | Commit | Version probed | License file | Role |
|---|---|---|---|---|
| bm25s | `cda938e95f7053b843ce3e3fe1678410be39095f` | 0.3.13 | `LICENSE` (MIT) | Lexical index |
| Faiss | `3c54e2efb891b1a317e69308097ba54122c3b033` | 1.13.0 `faiss-cpu` macosx_14_0_arm64 wheel, 3.4 MB | `LICENSE` (MIT) | Exact inner-product index |
| Vue | `5be58b4c475c1d14b4abacbfeda610394a0ee4e5` | 3.5.43 | `LICENSE` (MIT) | UI runtime |
| Nuxt | `2bfc2c87a6f3bb9b17b4b6a2e9c117ef06b278d4` | 4.4.8 | `LICENSE` (MIT) | UI shell |
| G6 | `54ece372b40aa8ecbf09add9e09544979a4be10f` | `@antv/g6` 5.1.1 | `LICENSE` (MIT) | Graph view |

Faiss depends on NumPy. The probe used the already installed NumPy 2.0.2 (`854252ded83e6b9c21c4ee80558d354d8a72484c`, `LICENSE.txt`, BSD-3-Clause). NumPy is not a second vector index.

The UI shell follows World Pub Monitor `976050d2d2aef2997864979c4518661487ef2563`, whose `apps/web/package.json` depends on `nuxt` `^4.4.8` and `@nuxt/ui` `^4.10.0`. That repository has no license file, so the application is not reused. Nuxt 4.4.8 depends on `vue` `^3.5.35`; the installed resolution probed here is Vue 3.5.43. `@nuxt/ui` 4.10.0 (`ada15803684c4a8eeced1a305d5d930484ccf82d`, `LICENSE.md`, MIT) was not loaded, so it stays a candidate.

P12 may call these libraries. This task does not add an app, a server, or a dependency manifest.

## Checks that passed

Device for all of these: the Apple M4 Max above.

- bm25s: `pip install --no-index --no-deps` of the local clone, then `BM25(method="lucene").index`, `retrieve`, `save`, and `load`. Three synthetic sentences. Query `citation science` returned id `w1`. Saved files: `corpus.jsonl`, `corpus.mmindex.json`, `data.csc.index.npy`, `indices.csc.index.npy`, `indptr.csc.index.npy`, `params.index.json`, `vocab.index.json`. Network was not required for this load. Cloning the repository earlier did use the network.
- Faiss: `pip install --only-binary=:all: faiss-cpu` (network required) installed 1.13.0. `IndexFlatIP(4).add/search` and `write_index`/`read_index` on four-dimensional synthetic float32 vectors. Top hit was row 0 with inner product 1.0. The index file was 93 bytes. Entry points read at the tag: `faiss/IndexFlat.h` `IndexFlatIP`, `faiss/index_io.h` `write_index` and `read_index`.
- Vue: `npm install --ignore-scripts vue@3.5.43` (network required). `createApp` returned an application object. `version` was `3.5.43`.
- Nuxt: same install, `nuxt@4.4.8`. `import('nuxt')` exposed `build`, `createNuxt`, and `loadNuxt`. `createNuxt` was not called and no port was opened.
- G6: same install, `@antv/g6@5.1.1`. `new Graph({ data: { nodes: [{ id: 'a' }] } })` constructed an object. `register` and `BaseLayout` are functions. `collapseElement`, `expandElement`, `focusElement`, `setElementVisibility`, `getElementVisibility`, and `getElementData` are functions on `Graph.prototype`. Those methods were not called. `ExtensionCategory.LAYOUT` is `"layout"`.

`rank_bm25` `BM25Okapi.get_scores` also ran, via `PYTHONPATH`, on the same three sentences (`0.093921`, `0.615313`, `0.0`). It is not the pin: the class has no `save`/`load`, and `pip install` of the shallow clone failed because `setup.py` runs `git describe` and this clone has no tags (`fatal: No names found, cannot describe anything`).

## Checkpoints (candidates, not adopted)

SPECTER2 code commit `fac1cb0940fe7bd3c0db00973f6889ca0b481b63`, `LICENSE.md` Apache-2.0. The runnable loader is `specter2_0/timo/interface.py` `Predictor`. `specter2_0/model.py` is a stub. `requires-python` is `>=3.8,<3.11`. The interface still imports `AutoAdapterModel` from `transformers`; the README imports it from `adapters`. Neither import was executed. `adapters` commit `53a1ea164c07498be7d522aed96c9e600aa3b38b` has `src/adapters/models/auto/adapter_model.py` `AutoAdapterModel` and an Apache-2.0 `LICENSE`. `import torch`, `transformers`, `adapters`, and `sentence_transformers` failed with `ModuleNotFoundError` on this machine.

Input construction in `Predictor.predict_one`: `title + sep_token + abstract` when an abstract is present, otherwise the title. `PredictorConfig.max_len` defaults to 512. Pooling is `last_hidden_state[:, 0, :]`. The base `config.json` has `hidden_size` 768, `max_position_embeddings` 512, `vocab_size` 31090, and `BertModel`. The tokenizer config has `sep_token` `[SEP]`, `do_lower_case` true, and `model_max_length` set to the unusable integer `1000000000000000019884624838656`. Callers must pass 512; they must not trust `model_max_length`.

| Checkpoint | Hub revision | Weight inspected by HEAD, not downloaded | Adapter config name |
|---|---|---|---|
| `allenai/specter2_base` | `3447645e1def9117997203454fa4495937bfbd83` | `pytorch_model.bin` 439740465 bytes | none |
| `allenai/specter2` (same revision as `allenai/specter2_proximity`; adapter configs identical) | `2081559630a80fc5851d8f798a05ba81e9468089` | `pytorch_adapter.bin` 3593365 bytes | `[PRX]` |
| `allenai/specter2_adhoc_query` | `3f4448817028388648a74349ece07af4518ec5bd` | `pytorch_adapter.bin` 3593365 bytes | `[QRY]` |

No Hub file list contained a `LICENSE` file. The proximity model card says "License: Apache 2.0" and "Finetuned from allenai/scibert_scivocab_uncased", and also says "bert-base-uncased + adapters". That last phrase disagrees with `vocab_size` 31090. The card line is not treated as a license file. Adapter `model_name` is `allenai/specter_plus_plus`, not `allenai/specter2_base`. `TaskType.PROXIMITY.name.lower()` is `proximity` and `ADHOC_QUERY` is `adhoc_query`, which are not the config names `[PRX]` and `[QRY]`. A load must set `load_as` explicitly. This was not run.

The code repository README states a base trained on citation triplets (described there as 6M triplets, SciNCL subset, max length 512) and adapters trained through SciRepEval. Those statements were not reproduced. Dataset licenses were not opened. `allenai/specter2_aug2023refresh` (`fb592d9375e91b996957c81824b30d32250c1a72`) is not the default base and was not selected.

## Multilingual candidate

Selected candidate: `intfloat/multilingual-e5-small`, revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`. `config.json`: BertModel, hidden size 384, `max_position_embeddings` 512, vocab size 250037. Tokenizer: `XLMRobertaTokenizer`, `model_max_length` 512, `do_lower_case` false. `modules.json`: Transformer, mean pooling, L2 normalize. `sentence_bert_config.json`: `max_seq_length` 512. `model.safetensors` is 470641600 bytes and was not downloaded.

The model card, not a license file, says `license: mit`. The card's training section says initialization from `microsoft/Multilingual-MiniLM-L12-H384`, weak supervision that includes S2ORC title/abstract and citation pairs, and supervised fine-tuning that includes English MS MARCO and Chinese DuReader Retrieval (86k pairs). It also says every input should start with `query: ` or `passage: `, including non-English text, and shows a Chinese query example. None of that was executed. Dataset licenses were not opened. Decision remains `candidate`.

Not selected, and not a generative LoRA: `BAAI/bge-m3` revision `5617a9f61b028005a4858fdac845db406aefb181` is a 24-layer model, hidden size 1024, `max_position_embeddings` 8194, and `pytorch_model.bin` is 2271145830 bytes. `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` has the same 470641600-byte safetensors class, pooling without a normalize module, and no retrieval prefix in the config files that were read. The user-reported 8B/32B/70B LoRA recipes are not paper-embedding encoders and were not downloaded.

## Topics, time, and platforms not adopted

BERTopic `9036123c97aaa9a6cc4bec4a6db1a7caf9209df6`, package version 0.17.4 in `pyproject.toml`, `LICENSE` MIT, `requires-python` `>=3.10`. This machine is Python 3.9.6, and `import bertopic` failed. Modules read, not imported:

- `bertopic/vectorizers/_ctfidf.py` `ClassTfidfTransformer` for class-level term weights.
- `bertopic/representation/_base.py` `BaseRepresentation.extract_topics` and `bertopic/representation/_keybert.py` `KeyBERTInspired` for naming.
- `bertopic/_bertopic.py` `BERTopic.hierarchical_topics`, which builds a scipy linkage over c-TF-IDF or topic embeddings. That is a clustering tree, not containment evidence and not a temporal link.

The whole package is not pinned. Only those three module groups are candidates for a later import on Python >=3.10.

BERTrend `4f85cafc3b55f75ba49ac49807999fbbe42ca2aa` is rejected. `LICENSE.md` is MPL-2.0. `pyproject.toml` requires Python `>=3.12` and pulls Torch, BERTopic, and LLM/news tooling. `bertrend/__init__.py` creates `~/.bertrend` directories on import and may load a `.env`. Time is `doc_groups` keyed by timestamp, with `granularity` in days (`BERTrend.get_periods`). `_merge_models` cosine-merges topic embeddings at `min_similarity` and sums document counts; topics below the threshold become new topic ids. That merge is not an evidence-backed temporal link and is not separate from containment. The repository was not forked.

`jkitchin/litdb` `86fdc5987a7a8db43a76370503e7a62250483cc9` (MIT `LICENSE`, version 2.2.1) stores its own libSQL file, `F32_BLOB` embeddings, and an FTS5 table, and it crawls OpenAlex into that schema. It does not read the lake contracts. There is no small adaptation that preserves the read-only archive, so it is rejected and not forked. `litdb/litdb` `c22af8de30ba51d3138653a71eae4be30e13f16a` (BSD-3-Clause `LICENSE`, version 0.0.33) is a SQLite/MySQL/PostgreSQL TypeScript driver (`src/index.ts`). It has no bibliometric index. Rejected.

Pyserini `b875d19a6ba5bd5d228e269a5f9ece3934c79360` (`LICENSE.txt`, Apache-2.0) is rejected for this pin. `import pyserini` failed, and this machine has no Java runtime (`Unable to locate a Java Runtime`). It is a JVM search platform, not the thin local index.

hnswlib `ca426729609b3221563047ceb269cc1213e0d376` and USearch `1e8a19253138510f35ee2c68dc641e5b5c83c7b5` have Apache-2.0 `LICENSE` files. They were not installed after `IndexFlatIP` worked. They stay candidates for an approximate index if a later measured corpus makes exact search too slow.

## Minimal integration

- P06 lexical index: `bm25s.tokenize` without assuming English stopwords are correct for scientific text, `BM25(method="lucene")`, `save`/`load` under the run directory. Record token counts. Do not pickle `rank_bm25`.
- P07 vectors: L2-normalized float32 vectors in a Faiss `IndexFlatIP` file written with `write_index`. Store `work_id` order beside the index. Do not switch to IVF or HNSW without a new probe. Encoder weights stay outside git.
- P07 encoders: do not load SPECTER2 or E5 until Torch is available without disturbing `vllm-fn`, the weight license file exists or the maintainer accepts the unverified card, and the adapter `load_as` strings are checked against `[PRX]` and `[QRY]`. E5 query and passage prefixes stay out of the SPECTER2 paper adapter.
- P10: c-TF-IDF, a representation model, and `hierarchical_topics` may be called later. The linkage output is not the containment contract.
- P11: do not import BERTrend. Temporal links stay an evidence object.
- P12: Vue 3.5.43 and Nuxt 4.4.8, loopback only. Register a G6 layout with `register("layout", "<type>", SubclassOfBaseLayout)`. Drive visibility with `setElementVisibility` / `getElementVisibility`. `packages/g6/src/index.ts` references an `at.alicdn.com` icon font; the data view must not depend on that CDN. Do not copy World Pub Monitor.

## Revisit

- Re-probe Faiss, bm25s, Vue, Nuxt, and G6 on a Spark device before claiming that machine can host them. Head free memory of 6 GB and worker free memory of 8 GB are still user-reported.
- Adopt a checkpoint only after a local load that records revision, adapter name, tokenizer, token count, truncation, peak memory, and a license file.
- If E5 Chinese retrieval fails on a real pilot, reconsider `bge-m3` only with a measured memory figure. Do not substitute a generative LoRA.
- If exact Faiss search is too slow on a real corpus, probe hnswlib or USearch and record that commit. Do not extrapolate from this 4-dimensional probe.
- If bm25s tokenization fails on titles, compare a scientific analyzer. Pyserini only after a measured ARM64 JVM index.
- `@nuxt/ui` 4.10.0 may be used after a load probe. It is not pinned now.
- A project `LICENSE` is a maintainer decision. Do not infer one from these dependencies.
