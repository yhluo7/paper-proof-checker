# paper-proof-checker 设计说明

> **历史文档（0.1 原型设计）。**
> 本文件记录 2026-07-20 的 0.1 原型设计，仅作历史参考，不再作为当前行为依据。
> 其中与 0.2 冲突的内容（PyMuPDF 依赖、单一检查模式、`candidate_block_id` 契约、
> 不含 `rules_version` 的 manifest 等）均已被取代。
> 当前行为以 [repo-docs/index.md](../../repo-docs/index.md) 与实际代码为准。
> 相关变更见 [repo-docs/change-log.md](../../repo-docs/change-log.md)。

## 目标

第一版检查DOCX论文内部的数值一致性，并将带引用的正文主张追溯到本地参考文献PDF中的具体证据原文。工具优先保证来源可回溯和失败状态透明，不追求自动覆盖所有论文格式。

## 架构

核心程序负责确定性工作：输入校验、DOCX/PDF解析、数值标准化、参考文献映射、候选证据检索、审核结果验证和报告生成。Codex或Claude Skill负责语义工作：识别结果性数值、判断候选是否是同一结果、拆分原子主张和判定引用支撑等级。

核心程序不调用模型API。一份 `SKILL.md` 同时供Codex和Claude Code使用，Codex额外读取 `agents/openai.yaml`。

## 数据流

1. `prepare`只读解析输入，并创建独立时间戳运行目录。
2. DOCX转为带结构位置的文档块；PDF转为带页码的文本段落。
3. 程序生成数值审核批次和引用审核批次。
4. Skill逐条审核并写入两个reviews文件。
5. `validate`检查枚举、覆盖率和证据原文是否能在指定PDF页重新定位。
6. 只有验证通过后，`report`才生成正式Markdown报告。

## 安全边界

不修改或复制输入文件，不执行宏和嵌入对象，不自动下载全文，不读取API Key。PDF缺失、加密、扫描或映射不唯一时只报告不可用，不推断引用不成立。

