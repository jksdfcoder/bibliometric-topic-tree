# ADR-001：复用采集路线，独立研究派生层

状态：数据审查后的有限范围决定；外部模型与前端技术选型尚未最终确定。

已审查基座：world_pub_monitor `976050d2d2aef2997864979c4518661487ef2563`。入口为 `apps/api/scripts/export-openalex-lake-jsonl.py`、`load-openalex-lake.ts`、`src/ingest/ingest.service.ts`、`src/flatten-work.ts`。流式导入、去重键与状态函数可借鉴；看板 schema 与机构汇总不能直接作为研究语料。工作区五个 worktree 不是同时 fork 多个平台。原库无变化。

比较三条路径：

1. **原始湖→独立只读抽取→版本化 JSONL/派生表（采用）。** 保留字段来源，部署成本低，支持现有数据路线。未知关系侧表的映射是当前缺口。
2. 扩看板 PostgreSQL 表：复用 API 较方便，但当前原始字段已丢弃，需回填/migration，且正式统计与实验耦合；本轮不采用。
3. 引入文献平台／图数据库：可能带来成熟检索模块，但增加同步、迁移、许可证与运行维护成本，现阶段不采用。

最小新代码为 `atlas_data.py`，JSONL 用标准库；Parquet 使用已可导入的 pyarrow；SQLite 仅作本 run 去重中间表，不是新图数据库。后续若用 DuckDB，应做只读扫描与格式性能对照，结果确认后再引入依赖。所有来源版本冲突都要显式消解，禁止下游静默“最后写入覆盖”。

当前代码 hash 写入每个 run manifest；新目录在父工作区不存在可取的 git HEAD，commit 可为 null，不捏造仓库版本。已有仓库 HEAD 单独在审查报告记录。

## 外部组件审查状态

SPECTER2、BERTopic、BERTrend、G6、litdb、S2AND 均**未在本轮完成源代码/commit/checkpoint/许可证审查或运行验证，未纳入实现依赖**。不得把候选 README 能力当本项目完成度。待真实语料可访问后，每个拟采用组件先记录精确 commit、实际入口及许可证文件；模型另外固定 checkpoint revision/adapter revision/训练来源与模型卡。没有版本与许可核查不部署、不分发。已有基座未找到 LICENSE 文件，private package 不构成许可；复用到外部分发前需确认代码权利。

后续最小核查清单：SPECTER2 proximity 与短 query adapter 的加载和输入长度；BERTopic 的论文分群/命名/层级是否可拆用；BERTrend 的状态链接证据与时间语义；G6 自定义时间半径布局与层级聚合计数；litdb 是否能适配现有存储。不同时 fork 多个平台，预训练模型、GNN 与训练集建设暂缓。
