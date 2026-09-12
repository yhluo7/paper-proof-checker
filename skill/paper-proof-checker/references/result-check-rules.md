# 数值审核规则

## 审核目标

判断正文中的数值是不是作者自己的研究结果，以及候选表格、表注或图注中的某个候选数值
是否表达同一个变量、统计指标、研究对象、亚组和时间点。

## 判断顺序

1. 先判断该数字是否为研究结果。年份、软件版本、注册号、方法阈值、章节或图表编号、
   引用他人研究的数值，标记为 `not_a_result`。
2. 再核对变量名称、统计指标、研究对象、亚组和时间点。
   **数值相同但语义对象不同，不得判为匹配。**
3. 候选列表里带 `relation` 字段的是核心程序已经算出的确定性关系。
   当候选中存在确定性关系时，优先采用确定性最强的那一条：
   - `exact_match`
   - `converted_match`（百分比与小数换算）
   - `rounded_match`（按显示精度四舍五入后一致）
   - `threshold_compatible`（如正文写 P<0.05、表格写 P=0.032）
4. 只有当多条候选具有同等强度的确定性关系、且无法靠上下文排除时，才使用 `ambiguous`。
   仅有 `potential_conflict` 的候选**不构成** `ambiguous` 的理由。
5. 明确是同一结果但数值不同，使用 `conflict`。
6. 正文明确指向图片、图片像素无法读取时，使用 `manual_figure_check`。
7. 其余没有任何候选的研究结果数值，使用 `source_not_found`。

## 候选数值的使用规则

- `candidate_number_id` 只能填当前检查 `candidates` 数组里出现过的 `number_id`。
- 选择 `exact_match`、`converted_match`、`rounded_match`、`threshold_compatible`、`conflict` 时**必须**提供候选。
- 选择 `source_not_found`、`not_a_result`、`manual_figure_check` 时**不得**提供候选。
- 不允许把任意文档块当作候选来源，候选只能来自当前检查返回的列表。

## 必须记录

- `check_id`
- `verdict`
- 选中候选时的 `candidate_number_id`
- 简短、具体的中文理由
- `high`、`medium` 或 `low` 置信度
- `needs_human_review`，必须是布尔值
