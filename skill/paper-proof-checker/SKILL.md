---
name: paper-proof-checker
description: Check a DOCX manuscript, optional DOCX supplement, and local reference PDFs for numerical consistency and citation support. Use when a user asks to audit paper results against tables or captions, trace cited claims to exact supporting PDF passages, or perform a final manuscript proof check with Codex or Claude Code.
---

# Paper Proof Checker

用本地 `paper-proof` 命令完成确定性解析与验证，只用模型推理判断两件事：
两个带上下文的数值是不是同一个结果，以及被引原文是否支撑一条原子主张。

## 工作流

1. 运行 `paper-proof --version`。若不可用，提示用户安装，不要用临时提示词替代解析器。
2. 确认输入：主文DOCX、可选补充材料、参考文献PDF目录。不要修改或复制用户的原始文件。
3. 按 [manuscript-input-rules.md](references/manuscript-input-rules.md) 选择模式并运行：
   - 只核对数值，或用户没有提供参考文献PDF：`paper-proof prepare <project> --checks numbers`
   - 核对引用或完整检查：`paper-proof prepare <project> --checks all`
   - 用户提供了映射文件：追加 `--reference-map reference-map.json`
4. 读取返回的运行目录，然后读取：
   - `batches/numeric.json`（启用 numbers 时）
   - `batches/citation.json`（启用 citations 时）
   - `reference-mapping.md`（启用 citations 时）
   - [result-check-rules.md](references/result-check-rules.md)
   - [citation-check-rules.md](references/citation-check-rules.md)
   - [output-schema.md](references/output-schema.md)
5. 逐条审核数值检查，写成 `reviews/numeric-reviews.json`，严格按 [output-schema.md](references/output-schema.md)。
6. 把每条引用批次拆成原子主张，只对照该引用编号指向的文献审核。
   初次候选证据不足时调用 `paper-proof search-evidence`，
   每条主张对每篇文献最多追加两次检索。
7. 写成 `reviews/citation-reviews.json`，严格按 [output-schema.md](references/output-schema.md)。
   只引用返回段落里看得见的原文。
8. 运行 `paper-proof validate <run-dir>`。修正错误只能靠重新阅读来源文件，
   绝不允许编造缺失的原文、页码、数值或参考文献。
9. 验证通过后运行 `paper-proof report <run-dir>`，
   返回报告路径与高风险发现的简要总结。

## 不可协商的边界

- 缺失、加密、扫描件或无唯一对应的PDF都算"全文不可用"，不算"没有支撑"。
- 不从图形像素里推断数值，标记为需要人工检查。
- 不把主题相关当作直接支撑。
- 判断支撑程度时保留人群、暴露、结局、方向、程度与时间范围等限定条件。
- 每条证据只保留一到三句逐字原文，并给出PDF页码与段落标识。
- 数值审核必须指向候选列表中真实存在的候选数值，不得使用任意文档块冒充来源。
- 说明：本地文件由核心程序处理；被审核的正文片段与候选证据按用户现有模型服务规则处理。
