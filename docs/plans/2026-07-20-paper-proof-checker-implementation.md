# paper-proof-checker 实施说明

> **历史文档（0.1 原型实施）。**
> 本文件记录 2026-07-20 的 0.1 原型实施顺序与接口，仅作历史参考。
> `prepare` 的参数集、PDF 解析库、审核 JSON 字段与验证规则均已在 0.2 变更，
> 本文件中的接口清单不再是当前接口契约。
> 当前行为以 [repo-docs/index.md](../../repo-docs/index.md) 与实际代码为准。
> 相关变更见 [repo-docs/change-log.md](../../repo-docs/change-log.md)。

## 已确定接口

- `paper-proof prepare <project>`：解析输入并生成审核批次。
- `paper-proof search-evidence <run-dir> --reference N --query TEXT`：在单篇被引PDF中补充检索。
- `paper-proof validate <run-dir>`：验证模型审核结果和证据可追溯性。
- `paper-proof report <run-dir>`：生成正式中文报告。
- `paper-proof install-skill --target codex|claude|both`：安装同一份Skill。

## 实施顺序

1. 建立Python包、CLI和Skill安装能力。
2. 实现DOCX结构解析、修订检测和Vancouver引用解析。
3. 实现PDF逐页解析和参考文献映射。
4. 实现数值标准化、候选匹配和词汇证据检索。
5. 实现审核JSON验证和Markdown报告。
6. 使用合成DOCX/PDF完成端到端自动测试。

## 延后内容

只有真实论文测试证明需要时，才增加PDF/LaTeX主文、OCR、图像取数、向量检索、MCP和网页界面。

