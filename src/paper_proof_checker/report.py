"""把已验证的结构化结果生成为中文Markdown终审报告。

0.2 变更：
- 只生成已启用模块的章节。
- 首屏给出作者行动摘要：冲突、部分支撑、缺失来源与人工检查。
- 增加解析覆盖率：正文块、表格、引用、参考文献匹配数以及明确未覆盖内容。
- 报告只使用项目相对路径，绝对路径仅保留在本地 manifest.json。
- 生成前重新核对输入文件与已匹配PDF的哈希。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .io_utils import read_json
from .validator import verify_hashes


NUMBER_LABELS = {
    "exact_match": "完全匹配",
    "converted_match": "换算后匹配",
    "rounded_match": "四舍五入后匹配",
    "threshold_compatible": "阈值兼容",
    "ambiguous": "存在多个可能来源",
    "conflict": "数值冲突",
    "source_not_found": "未找到对应来源",
    "manual_figure_check": "需要检查图片",
    "not_a_result": "非研究结果",
}
CITATION_LABELS = {
    "direct_support": "直接支撑",
    "inference_support": "推论支撑",
    "partial_support": "部分支撑",
    "background_only": "仅背景相关",
    "secondary_support": "二手支撑",
    "conflict": "与正文冲突",
    "evidence_not_found": "未找到有效证据",
    "full_text_unavailable": "全文不可用",
    "parse_failed": "解析失败",
    "manual_review": "需要人工判断",
}
NUMBER_RISK = {
    "conflict",
    "source_not_found",
    "ambiguous",
    "manual_figure_check",
}
CITATION_RISK = {"conflict", "partial_support", "background_only", "evidence_not_found"}
UNAVAILABLE_LABELS = {
    "missing_pdf": "本机未提供全文",
    "ambiguous": "未能唯一匹配全文",
    "parse_failed": "全文解析失败（加密、损坏或无文本层）",
}
DOCUMENT_LABELS = {"manuscript": "主文", "supplement": "补充材料"}
MAX_SUMMARY_ITEMS = 15


def _cell(value: object) -> str:
    """转义Markdown表格中的换行和竖线。"""

    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _shorten(text: str, limit: int = 80) -> str:
    """把长文本压成单行并按字符数截断，显式标记省略，避免出现半截条目。"""

    collapsed = " ".join(str(text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _document(document_name: str) -> str:
    return DOCUMENT_LABELS.get(document_name, document_name or "未知文档")


def _location(block: dict) -> str:
    """把DOCX结构位置转为作者可理解的文字。"""

    location = block.get("location", {})
    prefix = _document(block.get("document", ""))
    if "table_index" in location:
        return f"{prefix} 表{location['table_index']} 行{location['row']}列{location['column']}"
    return f"{prefix} {location.get('heading') or '未命名章节'} 第{location.get('paragraph_index')}段"


def _display_path(raw: str | None, project_dir: Path) -> str:
    """把绝对路径转成项目相对路径，避免报告泄露本机目录。"""

    if not raw:
        return "—"
    path = Path(raw)
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


def _evidence_text(review: dict) -> str:
    return "<br>".join(
        f"第{item.get('page')}页 {item.get('paragraph_id')} "
        f"{item.get('section') or '未标注章节'}：{item.get('quote', '')}"
        for item in review.get("evidence", [])
    )


def _coverage_section(
    document: dict,
    references: list[dict],
    number_reviews: list[dict],
    citation_reviews: list[dict],
) -> list[str]:
    """生成解析覆盖率与明确未覆盖内容。"""

    blocks = document.get("blocks", [])
    counts = Counter(block["document"] for block in blocks)
    table_keys = {
        (block["document"], block["location"].get("table_index"))
        for block in blocks
        if block["kind"] == "table_cell"
    }
    figure_keys = {
        (block["document"], block["location"].get("paragraph_index"))
        for block in blocks
        if block["kind"] == "figure_caption"
    }
    paragraph_count = sum(1 for block in blocks if block["kind"] == "paragraph")
    unmatched = [item for item in references if item["match_status"] != "matched"]

    lines = [
        f"- 文档块：{len(blocks)}（主文 {counts.get('manuscript', 0)}，补充材料 {counts.get('supplement', 0)}）",
        f"- 普通段落：{paragraph_count}",
        f"- 表格：{len(table_keys)}；表格单元格块：{sum(1 for b in blocks if b['kind'] == 'table_cell')}",
        f"- 图注块：{len(figure_keys)}",
    ]
    if references or citation_reviews:
        lines.append(f"- 正文引用标记：{len(document.get('citations', []))}")
        lines.append(
            f"- 参考文献条目：{len(references)}；已匹配本地全文："
            f"{len(references) - len(unmatched)}/{len(references)}"
        )
    if number_reviews:
        with_candidate = sum(1 for review in number_reviews if review.get("candidate_number_id"))
        lines.append(f"- 数值审核项：{len(number_reviews)}；其中给出候选来源：{with_candidate}")
    if citation_reviews:
        with_evidence = sum(1 for review in citation_reviews if review.get("evidence"))
        lines.append(f"- 引用审核项：{len(citation_reviews)}；其中附证据原文：{with_evidence}")

    uncovered: list[str] = []
    if figure_keys:
        uncovered.append(f"{len(figure_keys)} 个图注块对应的图形数值无法从像素读取，需要人工查看。")
    for reference in unmatched:
        label = UNAVAILABLE_LABELS.get(reference["match_status"], reference["match_status"])
        uncovered.append(
            f"参考文献{reference['reference_id']}：{label}"
            f"（{_cell(reference.get('raw_entry', ''))[:80]}）"
        )
    for review in number_reviews:
        if review.get("verdict") == "manual_figure_check":
            uncovered.append(f"数值检查{review['check_id']}：需要人工从图片读取。")
    for review in citation_reviews:
        if review.get("verdict") == "evidence_not_found":
            uncovered.append(
                f"引用检查{review.get('claim_id')}：全文可解析，但三轮检索未找到证据。"
            )
    lines.extend(["", "**明确未覆盖内容**", ""])
    lines.extend(f"- {item}" for item in uncovered) if uncovered else lines.append("- 无。")
    return lines


def build_report(run_dir: Path) -> Path:
    """仅使用已经通过validator的数据生成正式报告。"""

    manifest = read_json(run_dir / "manifest.json")
    enabled = manifest.get("enabled_checks", [])
    project_dir = Path(manifest.get("project_dir") or run_dir)

    document = read_json(run_dir / "document.json")
    references = (
        read_json(run_dir / "references.json").get("references", [])
        if "citations" in enabled
        else []
    )
    hash_errors = verify_hashes(manifest, references)
    if hash_errors:
        raise ValueError(
            "输入文件在prepare之后发生变化，禁止生成报告："
            + "；".join(hash_errors)
            + " 请重新执行prepare、validate、report。"
        )

    result_path = run_dir / "result-trace.json"
    citation_path = run_dir / "citation-evidence.json"
    if "numbers" in enabled and not result_path.exists():
        raise ValueError("尚未通过validate，不能生成正式报告。")
    if "citations" in enabled and not citation_path.exists():
        raise ValueError("尚未通过validate，不能生成正式报告。")

    number_reviews = read_json(result_path)["reviews"] if "numbers" in enabled else []
    citation_reviews = read_json(citation_path)["reviews"] if "citations" in enabled else []
    number_batch = (
        {
            item["check_id"]: item
            for item in read_json(run_dir / "batches" / "numeric.json")["checks"]
        }
        if "numbers" in enabled
        else {}
    )
    citation_batch = (
        {
            item["batch_id"]: item
            for item in read_json(run_dir / "batches" / "citation.json")["checks"]
        }
        if "citations" in enabled
        else {}
    )
    block_map = {block["block_id"]: block for block in document["blocks"]}

    unavailable = [item for item in references if item["match_status"] != "matched"]
    number_counts = Counter(item["verdict"] for item in number_reviews)
    citation_counts = Counter(item["verdict"] for item in citation_reviews)

    # 1. 作者行动摘要（首屏）。按风险从高到低登记，同一判断只保留一次。
    risks: dict[tuple[str, str], tuple[str, str, str, str]] = {}

    def add_risk(key: tuple[str, str], risk: str, location: str, subject: str, reason: str) -> None:
        risks.setdefault(key, (risk, location, subject, reason))

    for review in number_reviews:
        check = number_batch[review["check_id"]]
        label = NUMBER_LABELS[review["verdict"]]
        if review["verdict"] == "conflict":
            add_risk(
                ("number", review["check_id"]),
                label,
                _location(check["source_block"]),
                check["number"]["raw"],
                review["reason"],
            )
    for review in citation_reviews:
        if review["verdict"] != "conflict":
            continue
        add_risk(
            ("citation", review["claim_id"]),
            CITATION_LABELS[review["verdict"]],
            f"参考文献{review['reference_id']}",
            review["claim_text"],
            review["reason"],
        )
    for review in number_reviews:
        if review["verdict"] not in {"source_not_found", "ambiguous"}:
            continue
        check = number_batch[review["check_id"]]
        add_risk(
            ("number", review["check_id"]),
            NUMBER_LABELS[review["verdict"]],
            _location(check["source_block"]),
            check["number"]["raw"],
            review["reason"],
        )
    for review in citation_reviews:
        if review["verdict"] not in {"partial_support", "background_only", "evidence_not_found"}:
            continue
        add_risk(
            ("citation", review["claim_id"]),
            CITATION_LABELS[review["verdict"]],
            f"参考文献{review['reference_id']}",
            review["claim_text"],
            review["reason"],
        )
    for review in number_reviews:
        if review["verdict"] != "manual_figure_check":
            continue
        check = number_batch[review["check_id"]]
        add_risk(
            ("number", review["check_id"]),
            NUMBER_LABELS[review["verdict"]],
            _location(check["source_block"]),
            check["number"]["raw"],
            review["reason"],
        )
    for reference in unavailable:
        add_risk(
            ("reference", str(reference["reference_id"])),
            "全文不可用",
            f"参考文献{reference['reference_id']}",
            reference["match_status"],
            "缺少本地全文或未能唯一匹配，无法完成引用核查。",
        )
    covered_references = {str(reference["reference_id"]) for reference in unavailable}
    for review in list(number_reviews) + list(citation_reviews):
        if not review.get("needs_human_review"):
            continue
        if "check_id" in review:
            key = ("number", review["check_id"])
        else:
            if str(review.get("reference_id")) in covered_references:
                # 该参考文献已作为"全文不可用"登记，不再重复计入。
                continue
            key = ("citation", review.get("claim_id") or review.get("batch_id") or "")
        add_risk(key, "需人工确认", "—", "—", review.get("reason", ""))

    high_numbers = [item for item in number_reviews if item["verdict"] == "conflict"]
    high_citations = [item for item in citation_reviews if item["verdict"] == "conflict"]
    medium_citations = [
        item
        for item in citation_reviews
        if item["verdict"] in {"partial_support", "background_only", "evidence_not_found"}
    ]
    missing_source = [item for item in number_reviews if item["verdict"] == "source_not_found"]
    manual_items = sum(
        1
        for review in list(number_reviews) + list(citation_reviews)
        if review.get("needs_human_review")
    )

    summary = [f"- 明确数值冲突：{len(high_numbers)} 项。"]
    if "citations" in enabled:
        summary.append(f"- 引用结论冲突：{len(high_citations)} 项。")
        summary.append(
            f"- 需要核对引用的部分支撑、仅背景相关或未找到证据：{len(medium_citations)} 项。"
        )
    summary.append(f"- 正文数值未找到对应来源：{len(missing_source)} 项。")
    if "citations" in enabled:
        summary.append(f"- 缺少可用全文的参考文献：{len(unavailable)} 项。")
    summary.append(f"- 标记为需要人工确认的判断：{manual_items} 项。")
    summary.extend(
        [
            "",
            f"**总计需要作者处理的不同判断：{len(risks)} 项。** 下列条目按风险从高到低排列，",
            "完整矩阵见后续章节。所有判断均已通过验证器回溯检查。",
            "",
            "| 风险 | 位置 | 对象 | 理由 |",
            "|---|---|---|---|",
        ]
    )
    if not risks:
        summary.append("|—|—|未发现高风险问题|—|")
    for risk, location, subject, reason in list(risks.values())[:MAX_SUMMARY_ITEMS]:
        summary.append(f"|{_cell(risk)}|{_cell(location)}|{_cell(subject)}|{_cell(reason)}|")
    if len(risks) > MAX_SUMMARY_ITEMS:
        summary.append(f"|…|…|另有 {len(risks) - MAX_SUMMARY_ITEMS} 项见后续完整矩阵|…|")

    supplement_input = manifest.get("inputs", {}).get("supplement")
    sections: list[tuple[str, list[str]]] = [
        ("作者行动摘要", summary),
        (
            "输入文件与检查覆盖率",
            [
                f"- 运行时间：{manifest.get('created_at')}",
                f"- 检查模式：{'、'.join(enabled)}",
                "- 主文：`"
                + _display_path(
                    manifest.get("inputs", {}).get("manuscript", {}).get("path"), project_dir
                )
                + "`",
                "- 补充材料：`"
                + (_display_path(supplement_input.get("path"), project_dir) if supplement_input else "未提供")
                + "`",
                (
                    "- 参考文献目录：`" + _display_path(manifest.get("references_dir"), project_dir) + "`"
                    if manifest.get("references_dir")
                    else "- 参考文献目录：未使用（数值检查模式）"
                ),
                f"- 工具版本：{manifest.get('version')}；审核规则版本：{manifest.get('rules_version')}",
                "",
            ]
            + _coverage_section(document, references, number_reviews, citation_reviews),
        ),
    ]

    if "numbers" in enabled:
        rows = ["|位置|正文数值|判断|理由|", "|---|---:|---|---|"]
        for review in number_reviews:
            if review["verdict"] not in NUMBER_RISK:
                continue
            check = number_batch[review["check_id"]]
            rows.append(
                f"|{_cell(_location(check['source_block']))}|{_cell(check['number']['raw'])}|"
                f"{_cell(NUMBER_LABELS[review['verdict']])}|{_cell(review['reason'])}|"
            )
        if len(rows) == 2:
            rows.append("|—|—|未发现|—|")
        sections.append(("数值冲突与缺失来源", rows))

        rows = ["|检查ID|位置|原文|数值|候选数值ID|对应位置|状态|理由|", "|---|---|---|---:|---|---|---|---|"]
        for review in number_reviews:
            check = number_batch[review["check_id"]]
            candidate_id = review.get("candidate_number_id")
            candidate = next(
                (item for item in check.get("candidates", []) if item["number_id"] == candidate_id),
                None,
            )
            rows.append(
                f"|{review['check_id']}|{_cell(_location(check['source_block']))}|"
                f"{_cell(check['source_block']['text'])}|{_cell(check['number']['raw'])}|"
                f"{_cell(candidate_id or '—')}|"
                f"{_cell(_location(block_map[candidate['block_id']]) if candidate else '')}|"
                f"{_cell(NUMBER_LABELS[review['verdict']])}|{_cell(review['reason'])}|"
            )
        sections.append(("完整数值追溯矩阵", rows))

    if "citations" in enabled:
        rows = ["|主张|参考文献|状态|理由|", "|---|---:|---|---|"]
        for review in citation_reviews:
            if review["verdict"] not in CITATION_RISK:
                continue
            rows.append(
                f"|{_cell(review['claim_text'])}|{review['reference_id']}|"
                f"{_cell(CITATION_LABELS[review['verdict']])}|{_cell(review['reason'])}|"
            )
        if len(rows) == 2:
            rows.append("|—|—|未发现|—|")
        sections.append(("引用风险摘要", rows))

        rows = ["|检查ID|正文主张|正文原文|参考文献|判断|证据（段落与原文）|理由|", "|---|---|---|---:|---|---|---|"]
        for review in citation_reviews:
            rows.append(
                f"|{review['claim_id']}|{_cell(review['claim_text'])}|"
                f"{_cell(review.get('source_quote', ''))}|{review['reference_id']}|"
                f"{_cell(CITATION_LABELS[review['verdict']])}|{_cell(_evidence_text(review))}|"
                f"{_cell(review['reason'])}|"
            )
        sections.append(("完整引用证据矩阵", rows))

        rows = ["|编号|状态|匹配方式|参考文献|", "|---:|---|---|---|"]
        for reference in unavailable:
            rows.append(
                f"|{reference['reference_id']}|{_cell(reference['match_status'])}|"
                f"{_cell(reference.get('match_method') or '—')}|"
                f"{_cell(_shorten(reference.get('raw_entry', ''), 160))}|"
            )
        if len(rows) == 2:
            rows.append("|—|无|—|全部本地全文均已匹配|")
        sections.append(("无法完成全文检查的参考文献", rows))

    if "numbers" in enabled:
        figure_checks = [
            item for item in number_reviews if item["verdict"] == "manual_figure_check"
        ]
        rows = (
            [f"- {item['check_id']}：{item['reason']}" for item in figure_checks]
            if figure_checks
            else ["- 没有需要从图片像素人工读取的已识别项目。"]
        )
        sections.append(("图片人工检查清单", rows))

    sections.append(
        (
            "作者最终确认清单",
            [
                "- [ ] 核对全部高风险数值冲突。",
                "- [ ] 核对部分支撑、背景相关和冲突引用。",
                "- [ ] 补齐缺失或无法解析的参考文献全文。",
                "- [ ] 人工查看工具无法读取的图形数值。",
                "- [ ] 确认修改后重新运行检查。",
            ],
        )
    )

    boundary = [
        "本报告的所有判断都已通过验证器回溯检查：数值判断指向候选数值，"
        "引用判断指向参考文献的具体段落与页码。",
        "本工具提供可追溯的终审线索，不证明研究结论真实，也不替代作者、统计师或期刊编辑。",
        "核心程序不联网，但Codex或Claude进行语义审核时，"
        "相关正文与候选证据会按用户现有模型服务规则发送给模型提供方。",
        "",
        "### 状态计数",
        "",
    ]
    if "numbers" in enabled:
        boundary.append(f"- 数值：{dict(number_counts)}")
    if "citations" in enabled:
        boundary.append(f"- 引用：{dict(citation_counts)}")
    sections.append(("能力边界", boundary))

    lines = ["# 论文终审检查报告", ""]
    for index, (title, body) in enumerate(sections, start=1):
        lines.append(f"## {index}. {title}")
        lines.append("")
        lines.extend(body)
        lines.append("")

    report_path = run_dir / "paper-proof-report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path
