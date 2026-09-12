# quick-demo：五分钟复现一次完整检查

这是一个**完全虚构的合成论文项目**，用于公开复现 paper-proof-checker 的完整流程。
它不含任何真实论文内容，所有作者、期刊、DOI 与数值均为演示而编造。

## 目录内容

```text
quick-demo/
├── manuscript.docx          主文（含1张表、5条编号参考文献、5处引用）
├── supplement.docx          补充材料（提供88.4%的来源）
├── reference-map.json       参考文献编号到PDF文件的手工映射
├── references/
│   ├── Smith_2022.pdf       有DOI，可直接匹配
│   ├── Brown_2021.pdf       没有DOI且元数据标题不同，只能靠手工映射匹配
│   └── archive/
│       ├── Jones_2023.pdf   放在子目录里，用于验证递归发现
│       └── Chen_2020.pdf    同上
└── expected/
    ├── numeric-reviews.json 标准数值审核答案
    ├── citation-reviews.json 标准引用审核答案
    ├── paper-proof-report.md 由标准答案生成的正式报告
    ├── reference-mapping.md 参考文献匹配结果
    └── run-summary.json      运行规模摘要（不含本机绝对路径）
```

参考文献 **5（Miller 2019）故意没有提供PDF**，用于演示"全文不可用"必须被如实报告。

## 运行方式

```powershell
paper-proof prepare quick-demo --checks all --reference-map reference-map.json
paper-proof validate quick-demo/paper-proof-output/<时间戳目录>
paper-proof report quick-demo/paper-proof-output/<时间戳目录>
```

不需要参考文献目录时（只做数值检查）：

```powershell
paper-proof prepare quick-demo --checks numbers
```

## 这14项场景分别验证什么

| # | 场景 | 期望判断 | 高风险 |
|---:|---|---|:--:|
| 1 | 软件版本等非研究结果数值 | `not_a_result` |  |
| 2 | 正文与表格数值完全一致 | `exact_match` |  |
| 3 | 四舍五入后一致 | `rounded_match` |  |
| 4 | 百分比与小数换算一致 | `converted_match` |  |
| 5 | P值阈值与精确值兼容 | `threshold_compatible` |  |
| 6 | 同一结果数值不同 | `conflict` | ✔ |
| 7 | 数值没有任何表格或图注来源 | `source_not_found` | ✔ |
| 8 | 补充材料提供正文数值的来源 | `exact_match` |  |
| 9 | 数值只在图片里，像素无法读取 | `manual_figure_check` | ✔ |
| 10 | 正文主张被原文直接支撑 | `direct_support` |  |
| 11 | 原文只支撑特定亚组 | `partial_support` | ✔ |
| 12 | 原文结论与正文相反 | `conflict` | ✔ |
| 13 | 全文可解析但找不到证据 | `evidence_not_found` | ✔ |
| 14 | 参考文献没有本地全文 | `full_text_unavailable` | ✔ |

另有第15项结构性验证：`reference-map.json` 的手工映射优先于自动匹配，
且每条引用证据都能回到具体段落ID与真实PDF页码。

## 结果与边界

- 标准答案冻结在 `eval/ground-truth.json`，先于任何模型运行写好，之后不得修改。
- 本Demo是**合成数据**，无真实论文验证。它证明的是流程可复现、判断可回溯，
  不代表在真实论文上的表现。
- 预埋高风险问题共 7 项，用于计算高风险召回率与误报数。
- 场景总数为 14 项，用于计算总体判断准确率。
