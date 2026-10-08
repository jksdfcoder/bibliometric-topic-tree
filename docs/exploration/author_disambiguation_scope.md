# 作者消歧范围决定

建议：**当前延期；获得论文级 raw mentions 和独立核验样例后限定范围 pilot。** 地图与新文定位不依赖此模块。

依据：当前看板 schema 无原始署名/序位，lake exporter 把各作者机构聚合为单条 authorship，不能恢复身份。真实湖署名表来源/覆盖未验证；没有独立真值，也未审查 S2AND、Disamb/Jev 的实际代码/checkpoint/训练污染。不存在可报告的作者准确率或 B³。

`mentions.jsonl` 仅保存 work.authorships 的 raw name、raw affiliation strings、论文内原始列表位置、author_position 与 source_version；不读取 author.id、author.display_name、author.orcid、聚合机构/历史/合作网络。缺 raw name 保持 null，不拿实体姓名补。内容/顺序绑定 mention_id，变化产生新 mention，同一 person 的归属与版本对应尚未实现。ORCID/email 原始来源无法证明时不用作事实；当前直接不导入，不擅自读取既有正式消歧档案。

后续选少量独立证明的学者，建立 mention/profile comparison 与保守待核验；覆盖同名同方向、initial、迁移、多 email、无共同合作者、研究转向与误合并撤销。不同 email/单位/topic 不是排除规则。候选覆盖、误合并和漏并先分别报告；标签充分才报告 B³/all-pairs。五年且仅本领域语料的学者图只能称“近五年领域内轨迹”。
