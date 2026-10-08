# 实测与失败记录

2026-10-08：原始真实语料不可访问，所以无真实领域数量、摘要/参考覆盖、模型近邻、新文定位质量、准确率或吞吐结论。没有用 fixture/LLM/topic/citation 充当真值。

## 工程验证

`python3 -m unittest discover -s research/research_atlas/tests -v`：10 项通过，覆盖原生 Parquet、JSONL.gz、缺摘要/缺引用、外部引用端点、原始署名隔离、发表日期边界、更新版本去重后再筛选、分层计数与抽样重跑一致性、版本冲突失败 manifest、禁止源内输出/覆写。全部为明确构造的单元 fixture，仅证明适配器行为，不证明真实效果。pyarrow 读取合成测试 Parquet 成功，沙箱产生 CPU sysctl 探查警告，非模型或 GPU 性能测量。

既有采集 `openalex.client.ts` 通过 Node 24 strip-types 在 mock fetch 中复现：首响应 429 且缺 Retry-After，捕获 setTimeout 延时为 `[0]` 毫秒；请求不含 api_key。`syncProgressUpdate` incomplete pass 保持 priorWatermark 的本地断言通过。没有安装/运行旧仓库 Vitest 全套，也没有启动采集写生产数据库。

## 尚未排除的风险

- 本工具关键词/source 候选不能区分核心机制研究与应用 review；召回和精准度都未经标定。来源名变化、多语词不足或内容过于隐含可能漏召回。
- 分层只覆盖被召回候选；不能宣称全领域代表性。缺发表日期被排除并计数，需另建审查队列，不能自动用 created date 补上。
- 原始关系湖 side tables 未 inspect；单独主表会缺 abstract/reference/authorship。工具能报告缺失，但不能修复来源缺失。
- 完整 input hash＋解析是两次扫描；跨分片去重需要额外磁盘。大规模运行未测，不把工程实现当已验证低成本。
- [] references 是“来源报告为空”，不是事实零参考文献；只有 raw name 字段来源已隔离，不代表姓名或单位本身已独立核验。
- source_created_date 不等同研究系统首次发现；没有在线历史 snapshot 时无法复现过去的可见性。
- 当前 SQLite 中间表与 outputs 没有完全原子目录提交，失败保留部分文件并标 failed，下游必须检查 manifest。

## 下一轮必须呈现的困难例

同方法不同研究问题、应用型 bibliometric review、无摘要且引用丰富、摘要充分但引用缺失、双语检索、晚收录旧文、跨方向论文、五年窗外的重要前序论文、重复 DOI/预印本版本。逐例记录各路排名/缺失、人工意见、融合是否改善，并保留拒判理由。
