# 输入格式与模式选择

## 论文项目目录

```text
paper-project/
├── manuscript.docx          主文，必需
├── supplement.docx          补充材料，可选
├── reference-map.json       参考文献映射，可选
└── references/              参考文献PDF目录，citations与all模式必需
    ├── Smith_2022.pdf
    └── archive/
        └── Jones_2023.pdf
```

主文与补充材料必须是DOCX。存在未接受或未拒绝的修订痕迹时，
核心程序会拒绝继续，避免分析不可见的旧文字。

## 三种检查模式

`prepare` 的 `--checks` 参数决定要启用哪些模块，默认 `all`。

| 模式 | 必需输入 | 产物 |
|---|---|---|
| `numbers` | 主文DOCX；补充材料可选 | `batches/numeric.json` |
| `citations` | 主文DOCX + 参考文献目录 | `batches/citation.json`、`references.json` |
| `all` | 主文DOCX + 参考文献目录 | 以上全部 |

## 如何替用户选择模式

按顺序判断，不要反过来要求用户准备多余文件：

1. 用户只要求核对数值、表格、图注，或者**根本没有提供参考文献PDF**：使用 `--checks numbers`。
2. 用户明确要求核对引用，或要求"完整检查"：使用 `--checks all`，并在缺少参考文献目录时说明需要该目录。
3. 用户提供了参考文献目录但没有说明范围：使用 `--checks all`。
4. 用户提供的是 Word 主文与PDF文献，但没有补充材料：这是最常见的正常情况，`--supplement` 指向不存在的文件时会被自动忽略，不要因此报错。

禁止在没有参考文献PDF时声称"引用无法检查所以整体失败"；
应当运行 `--checks numbers`，并在结论中说明引用模块未启用。

## 参考文献映射文件

当PDF文件名与被引条目无法自动对应时，用户可以提供 `reference-map.json`：

```json
{
  "1": "Smith_2022.pdf",
  "2": "archive/Jones_2023.pdf"
}
```

规则：

- 键是被引编号（正整数）；值是相对参考文献目录的路径。
- 手工映射优先于自动匹配。
- 不存在文件、非PDF、同一文件重复分配、路径逃离参考文献目录都会被拒绝并给出明确报错。
- 未出现在映射文件中的条目继续使用自动匹配：DOI、PMID、标题、作者与年份。
- 不唯一匹配保持 `ambiguous`，核心程序不会替用户选择。
- PDF递归发现，扩展名大小写不敏感，支持子目录。

`prepare` 会额外生成 `reference-mapping.md`，供人工核对每一条对应关系。

## 输出目录

每次运行都会新建 `paper-proof-output/<北京时间戳>/`，不覆盖历史结果。
模型审核结果写入该目录的 `reviews/`，`validate` 与 `report` 只读取该目录。
