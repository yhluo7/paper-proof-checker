# 论文终审检查报告

## 1. 作者行动摘要

- 明确数值冲突：1 项。
- 引用结论冲突：1 项。
- 需要核对引用的部分支撑、仅背景相关或未找到证据：2 项。
- 正文数值未找到对应来源：1 项。
- 缺少可用全文的参考文献：1 项。
- 标记为需要人工确认的判断：7 项。

**总计需要作者处理的不同判断：7 项。** 下列条目按风险从高到低排列，
完整矩阵见后续章节。所有判断均已通过验证器回溯检查。

| 风险 | 位置 | 对象 | 理由 |
|---|---|---|---|
|数值冲突|主文 Results 第10段|41.2%|（标准答案）数值冲突。|
|与正文冲突|参考文献3|The intervention reduced mortality compared with usual care.|（标准答案）引用结论冲突。|
|未找到对应来源|主文 Results 第11段|6.3|（标准答案）数值无来源。|
|部分支撑|参考文献2|The intervention improved survival in every prespecified subgroup.|（标准答案）引用部分支撑。|
|未找到有效证据|参考文献4|The intervention reduced hospital admissions at one year.|（标准答案）已有全文但未找到证据。|
|需要检查图片|主文 Discussion 第15段|68.4%|（标准答案）图片人工检查。|
|全文不可用|参考文献5|missing_pdf|缺少本地全文或未能唯一匹配，无法完成引用核查。|

## 2. 输入文件与检查覆盖率

- 运行时间：2026-09-12T16:13:55+08:00
- 检查模式：numbers、citations
- 主文：`manuscript.docx`
- 补充材料：`supplement.docx`
- 参考文献目录：`references`
- 工具版本：0.2.0；审核规则版本：2

- 文档块：48（主文 42，补充材料 6）
- 普通段落：20
- 表格：2；表格单元格块：20
- 图注块：0
- 正文引用标记：5
- 参考文献条目：5；已匹配本地全文：4/5
- 数值审核项：9；其中给出候选来源：6
- 引用审核项：5；其中附证据原文：3

**明确未覆盖内容**

- 参考文献5：本机未提供全文（Miller R. Severe disease outcomes after the intervention. Journal of Trials. 201）
- 数值检查number-check-00009：需要人工从图片读取。
- 引用检查citation-check-00004-a：全文可解析，但三轮检索未找到证据。

## 3. 数值冲突与缺失来源

|位置|正文数值|判断|理由|
|---|---:|---|---|
|主文 Results 第10段|41.2%|数值冲突|（标准答案）数值冲突。|
|主文 Results 第11段|6.3|未找到对应来源|（标准答案）数值无来源。|
|主文 Discussion 第15段|68.4%|需要检查图片|（标准答案）图片人工检查。|

## 4. 完整数值追溯矩阵

|检查ID|位置|原文|数值|候选数值ID|对应位置|状态|理由|
|---|---|---|---:|---|---|---|---|
|number-check-00001|主文 Methods 第4段|All analyses were performed with version 4.2 of the statistics package.|4.2|—||非研究结果|（标准答案）非研究结果数值（软件版本）。|
|number-check-00002|主文 Results 第6段|At the one-year follow-up, mortality in the intervention group was 32.6%.|32.6%|num-00009|主文 表1 行2列2|完全匹配|（标准答案）完全匹配。|
|number-check-00003|主文 Results 第7段|The hazard ratio for all-cause mortality was 0.72.|0.72|num-00010|主文 表1 行2列3|四舍五入后匹配|（标准答案）四舍五入兼容。|
|number-check-00004|主文 Results 第8段|The response rate in the intervention group was 0.458.|0.458|num-00012|主文 表1 行3列2|换算后匹配|（标准答案）百分比与小数换算。|
|number-check-00005|主文 Results 第9段|The primary outcome met the prespecified significance criterion, P<0.05.|P<0.05|num-00011|主文 表1 行2列4|阈值兼容|（标准答案）P值阈值兼容。|
|number-check-00006|主文 Results 第10段|Mortality in the usual care group was 41.2%.|41.2%|num-00015|主文 表1 行4列2|数值冲突|（标准答案）数值冲突。|
|number-check-00007|主文 Results 第11段|The absolute risk reduction was 6.3 percentage points.|6.3|—||未找到对应来源|（标准答案）数值无来源。|
|number-check-00008|主文 Results 第12段|Adherence to the allocated treatment was 88.4% overall.|88.4%|num-00029|补充材料 表1 行2列2|完全匹配|（标准答案）补充材料提供来源。|
|number-check-00009|主文 Discussion 第15段|The survival estimates plotted in the supplementary figure show a long-term survival of 68.4%.|68.4%|—||需要检查图片|（标准答案）图片人工检查。|

## 5. 引用风险摘要

|主张|参考文献|状态|理由|
|---|---:|---|---|
|The intervention improved survival in every prespecified subgroup.|2|部分支撑|（标准答案）引用部分支撑。|
|The intervention reduced mortality compared with usual care.|3|与正文冲突|（标准答案）引用结论冲突。|
|The intervention reduced hospital admissions at one year.|4|未找到有效证据|（标准答案）已有全文但未找到证据。|

## 6. 完整引用证据矩阵

|检查ID|正文主张|正文原文|参考文献|判断|证据（段落与原文）|理由|
|---|---|---|---:|---|---|---|
|citation-check-00001-a|Treatment reduced all-cause mortality at one year in the treated group.|Treatment reduced all-cause mortality at one year in the treated group|1|直接支撑|第1页 p0001-b006 未标注章节：The intervention reduced all-cause mortality at one year in the treated group.|（标准答案）引用直接支撑。|
|citation-check-00002-a|The intervention improved survival in every prespecified subgroup.|The intervention improved survival in every prespecified subgroup|2|部分支撑|第1页 p0001-b006 未标注章节：In the subgroup of patients with diabetes, the intervention improved survival at one year.|（标准答案）引用部分支撑。|
|citation-check-00003-a|The intervention reduced mortality compared with usual care.|The intervention reduced mortality compared with usual care|3|与正文冲突|第1页 p0001-b005 未标注章节：The intervention did not reduce mortality compared with usual care at one year.|（标准答案）引用结论冲突。|
|citation-check-00004-a|The intervention reduced hospital admissions at one year.|The intervention reduced hospital admissions at one year|4|未找到有效证据||（标准答案）已有全文但未找到证据。|
|citation-check-00005-a|The intervention reduced mortality in patients with severe disease.|The intervention reduced mortality in patients with severe disease|5|全文不可用||（标准答案）参考文献全文缺失。|

## 7. 无法完成全文检查的参考文献

|编号|状态|匹配方式|参考文献|
|---:|---|---|---|
|5|missing_pdf|—|Miller R. Severe disease outcomes after the intervention. Journal of Trials. 2019. doi:10.1234/demo.5|

## 8. 图片人工检查清单

- number-check-00009：（标准答案）图片人工检查。

## 9. 作者最终确认清单

- [ ] 核对全部高风险数值冲突。
- [ ] 核对部分支撑、背景相关和冲突引用。
- [ ] 补齐缺失或无法解析的参考文献全文。
- [ ] 人工查看工具无法读取的图形数值。
- [ ] 确认修改后重新运行检查。

## 10. 能力边界

本报告的所有判断都已通过验证器回溯检查：数值判断指向候选数值，引用判断指向参考文献的具体段落与页码。
本工具提供可追溯的终审线索，不证明研究结论真实，也不替代作者、统计师或期刊编辑。
核心程序不联网，但Codex或Claude进行语义审核时，相关正文与候选证据会按用户现有模型服务规则发送给模型提供方。

### 状态计数

- 数值：{'not_a_result': 1, 'exact_match': 2, 'rounded_match': 1, 'converted_match': 1, 'threshold_compatible': 1, 'conflict': 1, 'source_not_found': 1, 'manual_figure_check': 1}
- 引用：{'direct_support': 1, 'partial_support': 1, 'conflict': 1, 'evidence_not_found': 1, 'full_text_unavailable': 1}

