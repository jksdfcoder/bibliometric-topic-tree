# Bibliometric Topic Tree

工程探索与真实数据原型：给定一篇新论文，定位细分研究方向、相关前序文献，并展示可检查的文本与引用证据。

**状态：实施目录与合同已建立，正式 pipeline 尚未实现。** 现有采集审查与有限分区实验工具保留为探索证据；它们不证明全五年提取、模型定位、topic 或研究演化已经完成。

- `main`：项目结构、架构/数据合同、配置模板、审查证据、历史实验工具。
- [`plan`](https://github.com/jksdfcoder/bibliometric-topic-tree/tree/plan/docs/plans)：逐步实施计划、任务依赖、模型分配模板和 review 标准。
- 实施分支：从 `main` 建 `impl/Pxx-short-name`；一项可审查任务一个 PR。具体模型由维护者分配，Codex 后续 review。

```text
src/atlas/          data / scope / retrieval / encoding / relations / positioning
                    topics / temporal / views / evaluation / incremental
apps/               api / web
configs/            data / models / relations / topics / views / evaluation / compute
schemas/            运行与定位结果的机器可读合同
scripts/            探查、验证和重跑入口（按计划实现）
tests/              unit / integration / ui / fixtures
annotation/         人工标注说明；真实标签保存在版本化run中
artifacts/          本地派生产物；语料、模型与向量不入Git
experiments/        历史探索工具，与正式pipeline隔离
docs/               architecture / exploration / decisions / reviews
```

先读 [架构](docs/architecture/overview.md)、[数据合同](docs/architecture/data_contracts.md)、[接口合同](docs/architecture/interfaces.md) 和 [执行约束](docs/architecture/constraints.md)。

## 开始实施

在 `plan` 分支读 `docs/plans/README.md`，只执行被分配的任务及其依赖已经通过的部分。计划中的CLI/模块路径是待实现接口，不是现有功能。读取 `AGENTS.md` 与 `CONTRIBUTING.md`，PR提供真实验证与失败记录；合成测试不代替真实语料结果。

历史工具工程检查（可选pyarrow；没有pyarrow会跳过Parquet测试）：

```sh
python3 -m unittest discover -s experiments/bootstrap_20261008/tests -v
```

该检查验证探索工具行为，不验证正式模型质量或完整领域覆盖。

## 数据与计算

复用现有只读OpenAlex关系湖和已有增量路线；不重建采集。首轮五年发表窗口在 `configs/data/pilot_scope.json` 固定。候选范围经人工审查区分核心、相邻、应用型和未知；OpenAlex topics只是reference。

训练不属于首轮必交。Spark资源文件是用户报告、未经独立测量；不自动停止推理服务、调时钟或假设双机统一内存。连接信息通过环境变量提供，凭据不入仓库。

代码/模型/数据许可证分别核查；当前未选择本项目公开许可。建立结构或公开仓库不表示第三方代码/模型已获重新分发许可。详见 `docs/decisions/README.md`。
