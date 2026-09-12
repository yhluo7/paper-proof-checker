# 引用证据审核规则

## 原子主张

把一句话拆成可分别判断真假的最小主张。不要删除人群、暴露、结局、方向、程度、时间和研究设计等限定条件。
一个引用范围包含多篇文献时，每篇文献分别审核。
每个原子主张都要用 `source_quote` 记录它在正文中的原话，验证器会复查该原话是否真的出现在对应正文块里。

## 支撑等级

- `direct_support`：原文明确报告同一主张及关键限定条件。
- `inference_support`：证据可以合理推出正文结论，但原文没有直接表达。
- `partial_support`：只支撑主张的一部分，或人群、程度、时间等范围更窄。
- `background_only`：主题相关，但不能证明该主张。
- `secondary_support`：综述或二手来源转述该结论。
- `conflict`：原文与正文方向、范围或结论明确冲突。
- `evidence_not_found`：**全文已成功解析**且最多三轮检索后仍未找到证据。
- `full_text_unavailable`：缺少PDF、未能唯一对应，或没有对应的参考文献条目。
- `parse_failed`：PDF加密、损坏或没有文本层。
- `manual_review`：证据复杂，模型无法可靠决定。

## 判断等级与全文可用性的绑定

- 没有全文（`missing_pdf`、`ambiguous`、`missing_reference_entry`）时，只能使用
  `full_text_unavailable` 或 `parse_failed`，**不得**使用 `evidence_not_found`，也不得给出任何支持性判断。
- `parse_failed` 只在参考文献状态为 `parse_failed` 时使用。
- 只有在参考文献状态为 `matched`（全文已成功解析）时，才允许使用 `direct_support`、
  `inference_support`、`partial_support`、`background_only`、`secondary_support`、
  `conflict`、`evidence_not_found`、`manual_review`。

## 证据要求

- 只使用当前引用编号对应的PDF。
- 每条证据必须同时给出：
  - `paragraph_id`：只能取自该文献解析结果中真实存在的段落标识；
  - `page`：必须等于该 `paragraph_id` 的真实页码；
  - `quote`：必须逐字出现在**那个段落内部**，只在同一页其他段落出现是不合格的。
- 引用一至三句连续原文，保留章节信息。
- 不能把摘要里的相关词汇当作结果证据。
- 支持、部分支撑、背景相关、冲突必须附证据；`evidence_not_found`、
  `full_text_unavailable`、`parse_failed` 不得附证据。
- 每条主张最多附三条证据。
