# 用户终端探查证据 — 2026-10-08

来源：用户在 `<lake-session>` 运行只读 pyarrow metadata probe 后提供的输出。Codex 自身尚无法 SSH，以下属于用户提供的真实元数据，不是本地独立读取记录所得。

- 系统 Linux Fedora 42 kernel 6.19.14，x86_64，pyarrow 可用。不能据此识别为 Spark，也尚未检查 GPU。
- `works` 190 个 Parquet 文件，样本包含 2016-06-24、2020-08-21、2025-11-11；最后样本 218,312 行。文件名排序的末分区为 2025-11-11，但未检查所有文件更新时间值、manifest 或发表日期覆盖，不能称更新到 2026。
- works 列有 int64 work ID、title/display_name、publication_date、created_date、updated_date（date）、updated（UTC microsecond timestamp）、abstract_inverted_index（Arrow map<string,list<int32>>）、type、DOI、retracted、language、authorships_truncated。精准版本比较优先 updated timestamp；日期单独用于侧表 join 诊断。
- `works_referenced_works` 342 文件，包含 work id / updated_date / referenced_work_id；2025-11-11 样本 1,417,492 行。有引用数据，但需要实际连接样例与版本审计，空行缺失不能推断事实零引用。
- `works_authorships` 251 文件，只有 work id / updated_date / author_position / author_id / is_corresponding；无 raw author name。
- `works_authorships_affiliations` 与 `works_authorships_institutions` 均 214 文件，只有 work id / updated_date / author_position / institution_id，无原始单位字符串。
- authors* 表含聚合姓名、作者 ID、ORCID、机构历史、主题与合作推断所需实体；按用户约束不读取这些字段解决作者身份。主线可不依赖身份继续。
- topics/concepts/keywords 表存在，不作为本次文本候选范围、模型输入、评测标签或主题树。
- `works_concepts/2025-11-06/data_13.parquet` 证明关系湖至少部分表确有多分片；既有只读 data_0 的 exporter 有实际 schema/组织上的遗漏风险。

## 已据此落地的适配

`atlas_data.py` 支持 Arrow map 转成 key/value pair list，不截断摘要；updated timestamp 优先于 date。新增 `lake_pilot.py`，只扫描显式指定的一个 works 更新分区所有分片，按五年发表日期＋标题/摘要线索召回待核验候选；侧表对相同分区、work ID、updated_date 做版本相容连接，显式说明来源/完整性未证实。不使用 author_id 或 resolved 身份。

输出与原始湖分离、新目录不可覆写、源码与源文件 hash、失败 manifest；缺引用侧表匹配行记 unknown。单分区内先消解版本再筛选。该阶段是字段与连接验证，不是全湖代表性 pilot，更不是完整五年抽取。全湖后续需在已验证性能/覆盖基础上按全分片版本消解、分层 pilot 与来源召回继续。

验证：新增真实 map schema、多分片 works、参考版本不符及领域外引用端点的合成工程测试；当前 12 项 unittest 通过，真实远端 pilot 尚未执行。提供终端接力命令，用户执行后以 counts/sample titles 与 manifest 核验是否可进行 BM25 基线。

## 引用方向与广字段归档更新

`works_referenced_works.id → referenced_work_id` 是 outgoing cited references；反向筛选 referenced_work_id 可得到该湖中的 incoming citations，没有单独 incoming 表的必要。counts_by_year、summary_stats 是聚合统计候选，但样本空表不能推断全表都空或引用数完备。当前新增可选所有 works_* 分区级源码字段归档及 partial incoming 输出；主表完整原始列默认归档，author_id 所在来源表单独 quarantine。尚未全湖扫描，因此不声称“所有信息已取齐”。

Spark 接入用户确认 `<spark-login>`；Codex 直接 SSH 非交互探查仍被环境网络拦截，没有认证、没有 GPU 硬件实测。
