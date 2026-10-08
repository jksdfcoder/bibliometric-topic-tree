# 来源字典 — P01

真实湖在本会话不可读。本文件区分三件事：代码准备识别的列、历史用户报告、以及这次探针实际读到的内容。合成测试夹具的行数和 `fixture-snapshot-9` 不写入这里。

## 这次测量

`python3 scripts/probe_source.py --root /opt/openalex --output artifacts/source-audit-001` 退出码 2。`/opt/openalex` 不存在，没有 fallback 下载。

| 项 | 结果 |
|---|---|
| 运行 | `artifacts/source-audit-001`（本地，不入 Git） |
| manifest 状态 | `blocked` |
| 是否测到表、schema、行数、覆盖率 | 否。`inventory.json` 中这些字段为 null |
| `source_version_fixed` | false |
| manifest 里的 `data.source_version` | 字符串 `unverified`，只表示尚未固定，不是 snapshot 日期 |
| `normalized_references_allowed` | false |
| 分区角色 | 未测。目录日期不能当成 snapshot 日期 |

因此没有任何研究字段具备已测到的来源表、列和版本依据。P03 的来源 join 不得开工。

## 缺的输入

- 可读的静态湖根（这次是 `/opt/openalex` 不存在）
- 唯一的 snapshot 或 conversion manifest（根目录文件名：`snapshot_manifest.json`、`conversion_manifest.json` 或 `source_snapshot.json`）
- 引用集版本语义、删除语义、空侧表语义
- 分区究竟是更新分区、全量 base 还是历史多版的证据

覆盖率未测，不填数字。删除条数没有独立计数。作者实体没有用来补 raw name 或单位字符串。来源 ID 没有解析成名称。

## 连接规则（在证明之前保持阻止）

- 侧表目录不存在，或 parquet 元数据行数为 0，都不是 `reported_empty`。空引用集必须来自该 work 修订上的显式空列表；当前没有这种证据。
- `updated` 时间戳比 `updated_date` 更精确。只有日期相同，或一边是 timestamp、一边只是 date，都不能把两侧当成同一引用集版本。
- 同一 work id 跨分区出现，即使 `updated` timestamp 相同，也不是引用集规则的证明。manifest 里非空的删除、引用集或空侧表句子本身也不是。timestamp 不一致，或同一分区里同一 id 出现多次，同样不能固定 `source_version`。
- 值样本每文件最多 32 行。元数据里的 `num_rows` 可以大于样本。样本没覆盖全部行，或读到的行里 work id 为空时，该文件样本不算完整，规范化连接保持阻止。这是代码上限，不是这次湖的测量。
- 只有一个根级 manifest 写明 `source_version`、`partition_role`（`update` / `full_base` / `historical_multi_version`）、`reference_set_semantics`、`deletion_semantics`、`empty_side_table_semantics`，并且 works 与 `works_referenced_works` 的全部行都读完、没有空 work id、同一 work id 不跨分区重复、且 timestamp 一致时，`inspect_source` 才把 `source_version_fixed` 和 `normalized_references_allowed` 设为 true。删除条数仍然不会被独立数出来。这次真实根目录没有进入该分支。

稳定读取方式：`atlas.data.inventory.inspect_source(root, output)`。下游只消费 `manifest.status == completed` 且 `normalized_references_allowed == true` 的运行。本 run 两者都不满足。

## 代码准备识别的列

下表是审计器会去找的列，不是已经在湖里看见的 schema。

| 字段 | 表 | 候选列 |
|---|---|---|
| work_id | works | id, work_id |
| title | works | title, display_name |
| abstract | works | abstract, abstract_inverted_index |
| publication_date | works | publication_date |
| source_created_date | works | created_date |
| source_updated_at | works | updated |
| source_updated_date | works | updated_date |
| type | works | type |
| doi | works | doi |
| referenced_work_id | works_referenced_works | referenced_work_id |
| raw_name | works_authorships | raw_author_name, raw_name |
| author_position | works_authorships | author_position |
| raw_affiliation | works_authorships_affiliations | raw_affiliation_strings, raw_affiliation |
| source_id | works | source_id |
| source_name | sources | display_name |

`authors*` 只做隔离：不读值，不用实体姓名或 ORCID 填补论文级 raw mention。`sources.display_name` 即使将来读到列名，在版本对齐证明之前也不能把 source id 当成刊名。

## 历史用户报告（未在本会话复测）

`docs/exploration/lake_schema_20261008.md` 记录用户在湖会话里提供的元数据，不是这次探针读盘的结果。其中提到 works、works_referenced_works、works_authorships、works_authorships_affiliations、works_authorships_institutions，以及 authorships 没有 raw author name、单位表没有原始单位字符串、`works_concepts/2025-11-06/data_13.parquet` 说明至少有一张表多分片。那些文件数、行数和列名在本 run 中都没有复测，不能当作当前 schema 或覆盖率。

采集仓库 commit `976050d2d2aef2997864979c4518661487ef2563` 与入口 `export-openalex-lake-jsonl.py`、`load-openalex-lake.ts`、`ingest.service.ts`、`flatten-work.ts` 来自 `reuse_and_architecture.md` 的历史审查。本会话没有重新打开该仓库。
