# 审核输出格式

所有文件使用UTF-8 JSON，顶层必须是 `reviews` 数组。
只写已启用模块对应的文件；不要为未启用的模块创建空文件。

## numeric-reviews.json（numbers / all 模式）

```json
{
  "reviews": [
    {
      "check_id": "number-check-00001",
      "verdict": "exact_match",
      "candidate_number_id": "num-00009",
      "reason": "正文与表格报告同一结局、亚组和时间点。",
      "confidence": "high",
      "needs_human_review": false
    }
  ]
}
```

- 每个 `check_id` 必须且只能出现一次。
- `candidate_number_id` 只能取自该检查 `candidates` 中的 `number_id`。
- 匹配类与冲突类判断必须给候选；`source_not_found`、`not_a_result`、
  `manual_figure_check` 必须为 `null` 或省略。
- `needs_human_review` 必须是布尔值。

## citation-reviews.json（citations / all 模式）

```json
{
  "reviews": [
    {
      "batch_id": "citation-check-00001",
      "claim_id": "citation-check-00001-a",
      "source_quote": "Treatment reduced all-cause mortality at one year in the treated group",
      "claim_text": "Treatment reduced all-cause mortality at one year in the treated group.",
      "reference_id": 1,
      "verdict": "direct_support",
      "evidence": [
        {
          "paragraph_id": "p0001-b006",
          "page": 1,
          "section": "Results",
          "quote": "The intervention reduced all-cause mortality at one year in the treated group."
        }
      ],
      "reason": "参考文献结果段直接报告同一结论。",
      "confidence": "high",
      "needs_human_review": false
    }
  ]
}
```

- 每个 `batch_id` 至少产生一条审核结果；拆分多个原子主张时使用不同且唯一的 `claim_id`。
- `source_quote` 必须是该正文块中逐字存在的片段（只做空白与大小写归一化）。
- `evidence[].paragraph_id` 必须存在于该参考文献的解析结果中，
  `page` 必须与之一致，`quote` 必须逐字出现在该段落内。
- `full_text_unavailable` 与 `parse_failed` 不得携带 `evidence`。
- 每条主张最多三条证据。

## 验证失败时

`paper-proof validate` 会返回非零退出码并写出 `validation-errors.json`。
修正方式只有一种：重新阅读 `batches/` 与参考文献解析结果，改写审核JSON。
不得编造原文、页码、数值或参考文献，也不得为了让验证通过而放宽判断。
