# AGENTS.md

本文件是仓库级协作约定，供人类协作者与AI编码助手共用。

## 文档入口

所有项目文档、命令索引、能力证据与变更流水集中在 [`repo-docs/`](repo-docs/index.md)。
在开始任何修改前，先读 `repo-docs/index.md`，再按需读 `repo-docs/evidence-index.md`。

## 硬性同步规则

以下规则对每一组实际修改都成立，不设例外：

1. **先读后写。** 修改任何模块前，先读 `repo-docs/index.md` 与相关模块，不要凭记忆推断接口。
2. **改完即记。** 每完成一组实际修改，立即在 `repo-docs/change-log.md` 追加一条记录，包含：
   - 北京时间（`YYYY-MM-DD HH:mm`）
   - 修改原因
   - 涉及文件
   - 完成内容
   - 验证状态（执行的命令与结果，未验证必须写明"未验证"）
3. **能力主张必须有证据。** 新增或修改任何对外可见的能力、限制或指标时，同步更新 `repo-docs/evidence-index.md`，
   给出代码位置、测试名称、Demo产物或命令。
4. **行为变更同步规则。** 只要改动了CLI参数、`manifest.json` 字段、审核JSON字段或报告结构，
   必须同时更新：`skill/paper-proof-checker/` 下的规则文件、`README.md`、`repo-docs/real-workflow.md`。
5. **规则版本。** 任何会使旧运行目录失效的契约变更，必须提升 `manifest.json` 的 `rules_version`，
   并让验证器显式拒绝旧版本，提示重新执行 `prepare`。
6. **不做无证据的宣称。** README 与报告不得宣称已在真实论文上验证、不得宣称能证明结论正确、
   不得把合成数据表现等同于真实论文表现。参见 `README.md` 中"不宣称"清单。
7. **不提交本地数据。** 真实论文、个人绝对路径、API Key、运行目录和构建产物一律不得进入提交。
   提交前执行 `repo-docs/evidence-index.md` 中"发布前检查"一节的命令。

## 本地开发约定

- Python 3.11 及以上；运行依赖只有 `python-docx` 与 `pypdf`（MIT/BSD 兼容许可）。
- 核心程序不联网、不读取API Key、不修改用户的输入文件。
- 测试必须可在无网络、无真实论文的条件下运行，全部输入由合成脚本生成。
- 生成合成PDF只允许使用 `pypdf` 与标准库，不引入 ReportLab 等新依赖。
