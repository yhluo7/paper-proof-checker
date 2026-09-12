"""提取、标准化并匹配论文中的数值候选。"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


P_VALUE = re.compile(r"\b[Pp]\s*([<=>≤≥])\s*(0?\.\d+|1(?:\.0+)?)")
PERCENTAGE = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?\s*%")
# 句末的小数（如"The HR was 0.72."）必须能被识别；
# 同时用 (?!\.\d) 排除版本号或章节号一类的小数链（如 1.2.3）。
NUMBER = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?!\.\d)(?!\w)")
FIGURE_REFERENCE = re.compile(r"\b(?:figure|fig\.)\s*\w+|图\s*\w+", re.I)
SOURCE_KINDS = {"table_cell", "table_caption", "table_note", "figure_caption"}
CONTEXT_STOPWORDS = {
    "the", "and", "was", "were", "with", "for", "from", "this", "that", "table",
    "figure", "results", "result", "value", "values", "month", "months", "year", "years",
}
# 表格、图、章节的编号属于文档结构，不是研究结果，也不应成为数值来源。
LABEL_PREFIX = re.compile(
    r"(?:tables?|figures?|figs?\.?|sections?|appendices?|supplements?|附录|附表|附图|表|图)\s*$",
    re.I,
)
P_VALUE_HEADER = re.compile(r"(?:p\s*[-–]?\s*values?|p值|p)", re.I)
EFFECT_HEADER = re.compile(r"(?:hr|or|rr|hazard\s+ratio|odds\s+ratio|β|beta)", re.I)


def _precision(raw: str) -> int:
    """返回显示小数位数。"""

    numeric = raw.replace("%", "").strip()
    return len(numeric.rsplit(".", 1)[1]) if "." in numeric else 0


def _is_label_number(text: str, start: int) -> bool:
    """判断数值是否只是"Table 1""Figure 2"这类结构编号。"""

    return bool(LABEL_PREFIX.search(text[max(0, start - 20) : start]))


def _number_type(text: str, start: int, raw: str, column_header: str = "") -> str:
    """依据数值附近的统计标签与所在列标题做保守分类。"""

    prefix = text[max(0, start - 25) : start].lower()
    context = text[max(0, start - 25) : start + len(raw) + 15].lower()
    header = (column_header or "").strip()
    if "%" in raw:
        return "percentage"
    if re.search(r"\b(?:hr|or|rr|beta|β)\s*[=:]?\s*$", prefix):
        return "effect_estimate"
    if re.search(r"\b(?:auc|c-index|sensitivity|specificity|brier)\b", context):
        return "model_metric"
    if re.search(r"\b[nN]\s*[=:]\s*$", text[max(0, start - 5) : start]):
        return "sample_size"
    if header and P_VALUE_HEADER.fullmatch(header):
        return "p_value"
    if header and EFFECT_HEADER.fullmatch(header):
        return "effect_estimate"
    return "number"


def extract_numbers(block: dict) -> list[dict]:
    """从一个文档块提取非引用编号的数值。"""

    text = block["text"]
    occupied: list[tuple[int, int]] = []
    records = []

    for match in P_VALUE.finditer(text):
        raw = match.group(0)
        records.append(
            {
                "raw": raw,
                "value": float(Decimal(match.group(2))),
                "type": "p_value",
                "precision": _precision(match.group(2)),
                "comparator": match.group(1).replace("≤", "<").replace("≥", ">"),
                "block_id": block["block_id"],
                "start": match.start(),
            }
        )
        occupied.append(match.span())

    for pattern in (PERCENTAGE, NUMBER):
        for match in pattern.finditer(text):
            if any(start <= match.start() < end for start, end in occupied):
                continue
            # 括号或方括号内的纯整数优先视为引用编号。
            if match.start() > 0 and match.end() < len(text):
                if text[match.start() - 1] in "[(,;" and text[match.end()] in ")] ,;–—-":
                    continue
            if _is_label_number(text, match.start()):
                continue
            raw = match.group(0).strip()
            try:
                value = Decimal(raw.replace("%", "").strip())
            except InvalidOperation:
                continue
            if "%" not in raw and value == value.to_integral() and 1900 <= value <= 2100:
                continue
            record_type = _number_type(
                text, match.start(), raw, block.get("column_header", "")
            )
            normalized = value / 100 if record_type == "percentage" else value
            # 百分数转为0到1后，小数精度相应增加两位，例如32.6%对应0.326。
            precision = _precision(raw) + 2 if record_type == "percentage" else _precision(raw)
            records.append(
                {
                    "raw": raw,
                    "value": float(normalized),
                    "type": record_type,
                    "precision": precision,
                    "comparator": "=",
                    "block_id": block["block_id"],
                    "start": match.start(),
                }
            )
            occupied.append(match.span())
    return sorted(records, key=lambda item: item["start"])


def compatibility(left: dict, right: dict) -> str | None:
    """返回两个数值的确定性兼容关系；语义同一性留给模型判断。"""

    if left["type"] == "p_value" and right["type"] == "p_value":
        if left["comparator"] == "<" and right["comparator"] == "=":
            return "threshold_compatible" if right["value"] < left["value"] else None
        if right["comparator"] == "<" and left["comparator"] == "=":
            return "threshold_compatible" if left["value"] < right["value"] else None
    if left["value"] == right["value"]:
        if {left["type"], right["type"]} == {"percentage", "number"}:
            return "converted_match"
        return "exact_match"
    precision = min(left["precision"], right["precision"])
    # 精度为整数位时四舍五入会把任何小数都归到0或1，属于无意义匹配，必须排除。
    if precision >= 1 and round(left["value"], precision) == round(right["value"], precision):
        return "rounded_match"
    return None


def _context_overlap(left: str, right: str) -> int:
    """计算去除数字和常见虚词后的上下文词重合数。"""

    def tokens(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-zA-Z][a-zA-Z-]+|[\u4e00-\u9fff]+", text.lower())
            if len(token) > 2 and token not in CONTEXT_STOPWORDS
        }

    return len(tokens(left) & tokens(right))


def build_number_batch(blocks: list[dict]) -> list[dict]:
    """为正文数值生成表格/图注候选，供模型逐条审核。"""

    block_map = {block["block_id"]: block for block in blocks}
    all_numbers = [
        {**number, "number_id": f"num-{index:05d}"}
        for index, number in enumerate(
            (number for block in blocks for number in extract_numbers(block)), start=1
        )
    ]
    source_numbers = [
        number
        for number in all_numbers
        if block_map[number["block_id"]]["kind"] in SOURCE_KINDS
    ]
    batch = []
    for number in all_numbers:
        block = block_map[number["block_id"]]
        if block["kind"] in SOURCE_KINDS or REFERENCE_SECTION(block.get("section", "")):
            continue
        candidates = []
        for source in source_numbers:
            relation = compatibility(number, source)
            source_block = block_map[source["block_id"]]
            overlap = _context_overlap(
                block.get("context_text", block["text"]),
                source_block.get("context_text", source_block["text"]),
            )
            # ponytail: 当前按单篇论文做二次扫描；数值超过数万时再改为倒排索引。
            if relation or overlap:
                candidates.append(
                    {
                        "number_id": source["number_id"],
                        "block_id": source["block_id"],
                        "raw": source["raw"],
                        "relation": relation or "potential_conflict",
                        "context_overlap": overlap,
                        "source_text": source_block.get("context_text", source_block["text"]),
                        "location": source_block["location"],
                    }
                )
        candidates.sort(
            key=lambda item: (
                item["relation"] == "potential_conflict",
                -item["context_overlap"],
                item["block_id"],
            )
        )
        candidates = candidates[:12]
        default_status = "ambiguous" if candidates else "source_not_found"
        if not candidates and FIGURE_REFERENCE.search(block["text"]):
            default_status = "manual_figure_check"
        batch.append(
            {
                "check_id": f"number-check-{len(batch) + 1:05d}",
                "number": number,
                "source_block": block,
                "candidates": candidates,
                "default_status": default_status,
            }
        )
    return batch


def REFERENCE_SECTION(section: str) -> bool:
    """识别参考文献章节，避免把年份等条目信息当作研究结果。"""

    return section.strip().lower() in {"references", "bibliography", "参考文献"}
