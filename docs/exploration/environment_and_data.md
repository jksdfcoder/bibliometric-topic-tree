# 环境、数据与采集审查 — 2026-10-08

## 已验证范围

主仓库 `<existing-monitor-repository>`，commit `976050d2d2aef2997864979c4518661487ef2563`，工作树审查时干净。其余五个同名前缀目录是同一仓库的 git worktree，不是五个平台。重点读取实际 exporter、loader、flatten、Prisma schema、API client、sync service 和状态函数，未据 README 宣称在线功能已成功。

本机为 macOS 26.5.2 ARM64，Node 24.15.0、Python 3、pyarrow 可导入；duckdb、torch、sentence_transformers 不可导入；API 的本地 node_modules 不存在。因此未运行既有 Vitest 全套，未启动 Nest 服务或数据库。新增适配器 unittest 可以本地运行。

工作区未找到原始 Parquet/JSONL/CSV 语料，本机 `/opt/openalex` 不存在。DATA.md 记载关系湖 `<lake-host>:/opt/openalex`，这是文档信息，未验证当前内容/权限/版本。现有 SSH 别名 `<other-ssh-alias>`、`<spark-ssh-alias>` 的非交互只读连接均被环境拒绝：`Operation not permitted`，不是已证实远端离线。没有绕过网络限制、请求密码、修改 SSH 配置或读取 secret。两机是否 DGX Spark、CUDA/驱动/PyTorch/显存和连线未验证。

## 可复用基础

- API 以 OpenAlex work ID upsert，避免简单重复插入；API cursor 按页保存，`syncProgressUpdate` 在未完成 pass 时保持既有 watermark，方向正确。
- JSONL loader 采用流读取与批量 SQL；非空库默认跳过，防止误启动冷加载；无 truncate。
- 对未来发表日期的 watermark 有 clamp；未把缺 topic 的论文一律删除。
- snapshot/bootstrap 与 API 路径分开、有页数上限和 data_revision，已有若干细粒度测试。

## 审查发现（代码位置相对于主仓库）

| 优先级 | 证据与触发条件 | 影响 | 最小改进建议 |
|---|---|---|---|
| P0 | `src/flatten-work.ts` 的 OpenAlexWork/WorkRow 与 `prisma/schema.prisma` 未保存摘要、references、raw names、updated date；exporter 139–169 只选少量列，239 附近把机构压成一条虚构 authorship | 看板统计可用，不能支撑语义＋引用实验或作者身份；已丢弃的字段不可逆恢复 | 原始湖只读，单独研究抽取，不给看板表强加身份模型；机构压缩不能当论文署名 |
| P0 | `src/ingest/openalex-plan.ts` 用 publication watermark（默认）或 created watermark（Premium） | 默认漏迟收录旧文与修订；created 模式也漏已有记录修订，不能称完整每日增量 | 先检查已有权限；有变更过滤权限则基于 updated-date bounded pass＋重叠去重；无权限按 snapshot 校正与明确的覆盖审计，不购买权限 |
| P0 | `scripts/load-openalex-lake.ts:221` 在 LOAD_LIMIT 到达时仍调用 finishLakeLoad；125–142 对已导入子集取 max 日期并 seed 水位 | 若最新日期先出现，会把未导入区间误当完整，跳过后续 bootstrap | capped run 不提升完整性状态／水位；另存覆盖 manifest，完整校验后才能 seed |
| P1 | `scripts/export-openalex-lake-jsonl.py:136,172,180,187` 每表每分区只读 data_0.parquet | 只要分区含 data_1 等文件就静默漏数；实际湖是否多分片尚待查 | 枚举所有分片，流式 batch/投影/日期 pushdown，先核对 schema 与各表 join 基数 |
| P1 | exporter 130 用 gzip.open(...,'wt')，文件名只含日期下界＋类型 | 重跑覆盖旧导出，不能重现版本或保留实验 | 新 run 目录、写临时文件再原子完成、记录 snapshot/代码/配置与 hash |
| P1 | `src/ingest/ingest.service.ts:122–133` 每次重算 bootstrap 下界；cursor 无 query hash 或固定 pass 范围 | INITIAL_WINDOW_DAYS 随天变化或跨年 year−2 变化时，恢复 cursor 搭配不同查询 | 固定 pass filter、上下界、分页 query hash，恢复必须一致 |
| P1 | client 以 mailto 作为接入，无 api_key 支持；DATA.md 用旧 polite pool 表述 | 不能据旧文档假定当前授权、限额和热更新可用 | 接入 env key（脱敏），读实际余额/权限/响应；按当前官方规则验证 |
| P1 | `src/ingest/openalex.client.ts:28` Number(null) 等于 0 | 429 没有 Retry-After 时实际立即重试，已本地复现 `[0]` ms | 区分 header 缺失、秒数、HTTP 日期；有上限的指数退避＋jitter；请求 timeout，谨慎重试 5xx/网络错误 |
| P1 | loader 批量 INSERT 同一 batch 如含同 work 多版本；输入遍历 readdir 不排序；exporter 无跨分区版本消解 | Postgres 单语句重复冲突目标可能报错；较旧版本可能覆盖新记录 | 按 updated date/来源版本先消解，冲突失败，固定遍历顺序 |
| P2 | sync.service 的 running 是进程布尔值；逐 work upsert，checkpoint 在页末 | 多实例可并发覆盖 cursor；失败重跑虽可 upsert，但统计或 revision 可能反映半完成 pass | DB advisory lock／租约；批量事务保证页数据与 checkpoint 一致，完成度与 freshness 分开 |
| P2 | exporter 只做发表下界，loader 同样缺上界；默认 year−2 不是五年 | 含未来日期；五年样本覆盖不足 | 显式固定 publication start/end；分区更新日期不得代替发表日期 |

以上是审查结论；未修改现有生产采集代码或数据库。P0/P1 中静态风险不等于已经观察到生产数据损坏。

## 字段来源报告

| 字段 | 当前看板表 | 原始记录要求与处理 |
|---|---|---|
| 论文 ID、标题、发表日期 | 有 | work ID 作为来源标识；发表日期定时间半径 |
| 摘要 | 无 | 原文或 inverted index 复原，不截断；空缺/位置缺口分开 |
| 参考文献 | 无 | referenced_works 或经验证引用侧表；null 与显式 [] 分开，[] 也不证明真实零引用 |
| 更新时间 | 无 | source updated date，按 UTC 比较；含被引数变化，不能等同内容改变 |
| 首次发现日期 | 无 | 本系统实际观察日志；缺历史日志则未知，created date 单独保存 |
| 原始署名、序位、raw affiliation | 无 | 只能从 work authorships raw 字段／已验证侧表读取 |
| ORCID/email | 未保留 | 当前抽取不使用 resolved author.orcid；需论文级来源独立证明 |
| OpenAlex topics | 主 topic 名称 | 完整 reference 隔离；不参与筛选、编码、标签或主题树 |
| 原始版本／内容 hash | 无完整版本 | 输入文件 SHA256、source_version、work raw hash、title/abstract hash |

真实规模、年份跨度、各年度摘要/引用覆盖率、raw mention 覆盖、湖最近更新与缺失偏差均未知。不能用 README 或单个 fixture 推断。用户随后确认湖入口为 `<lake-login>:/opt/openalex`；已直接进行非交互只读连接，仍返回 `Operation not permitted`（认证前连接被拒），未登录、未执行账户密码修改，也未保存凭据。缺失输入：可读静态原始切片/目录；关系表 schema 与 key 定义；snapshot manifest/版本；获授权的 Spark 接入信息；独立人工核验样例。

官方资料（2026-10-08 核查）：[Authentication](https://help.openalex.org/api/authentication/)、[Deprecations](https://help.openalex.org/api/deprecations/)、[Sync filters](https://help.openalex.org/api/filtering/)、[Authorships](https://help.openalex.org/data/authorships/)、[Works attributes](https://help.openalex.org/data/works/attributes/)。当前官方 Authentication 提及无 key 预算与免费 key 预算，而 Deprecations 使用“all users need a key”措辞；无论如何 mailto polite pool 已被替换，实际可用性应以账号权限及只读响应验证，不以旧限额猜测。

## 双 Spark 用户报告更新

用户提供当前资源/时钟与训练配方评估，详见 compute_constraints.md 与 configs/compute/reported_constraints.json。head/worker均121 GB统一内存，当前仅余6/8 GB；磁盘余2.2/2.4 TB；head时钟611 MHz、worker2398 MHz；vllm-fn占用中。属于用户报告，未独立实测。不能把湖机架构当Spark架构，也不能把双机内存算作可直接统一访问的242 GB。当前不停止服务或启动训练。
