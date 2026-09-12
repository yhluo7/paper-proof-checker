"""在指定被引PDF内进行轻量词汇检索。"""

from __future__ import annotations

import re
from pathlib import Path

from .io_utils import read_json


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "were",
    "with", "we", "our", "their", "has", "have", "had",
}


def _tokens(text: str) -> list[str]:
    """生成保留数字的英文检索词；中文连续文本按字符块保留。"""

    return [
        token
        for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", text.lower())
        if len(token) > 1 and token not in STOPWORDS
    ]


def search_pdf_text(text_path: Path, query: str, limit: int = 8) -> list[dict]:
    """使用词重合、短语和章节加权返回候选证据段落。"""

    parsed = read_json(text_path)
    if parsed.get("status") != "parsed":
        return []
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    query_set = set(query_tokens)
    bigrams = {" ".join(query_tokens[index : index + 2]) for index in range(len(query_tokens) - 1)}
    scored = []
    for page in parsed.get("pages", []):
        for paragraph in page.get("paragraphs", []):
            text = paragraph["text"]
            lowered = text.lower()
            paragraph_tokens = set(_tokens(text))
            overlap = len(query_set & paragraph_tokens)
            if not overlap:
                continue
            score = overlap / max(len(query_set), 1)
            score += sum(0.2 for phrase in bigrams if phrase in lowered)
            if re.search(r"results?|findings?|outcomes?", paragraph.get("section", ""), re.I):
                score += 0.1
            scored.append(
                {
                    "page": paragraph["page"],
                    "section": paragraph.get("section", ""),
                    "paragraph_id": paragraph["paragraph_id"],
                    "text": text,
                    "score": round(score, 4),
                }
            )
    scored.sort(key=lambda item: (-item["score"], item["page"], item["paragraph_id"]))
    return scored[: max(1, min(limit, 20))]


def build_citation_batch(document: dict, references: list[dict]) -> list[dict]:
    """为每个正文引用和每篇被引文献分别生成审核项。"""

    block_map = {block["block_id"]: block for block in document["blocks"]}
    reference_map = {item["reference_id"]: item for item in references}
    batch = []
    for citation in document["citations"]:
        block = block_map[citation["source_block_id"]]
        query = block["text"].replace(citation["raw"], " ")
        for reference_id in citation["reference_ids"]:
            reference = reference_map.get(reference_id)
            candidates = []
            unavailable = "missing_reference_entry"
            if reference:
                unavailable = reference["match_status"]
                if reference["match_status"] == "matched":
                    candidates = search_pdf_text(Path(reference["text_path"]), query, limit=8)
            batch.append(
                {
                    "batch_id": f"citation-check-{len(batch) + 1:05d}",
                    "source_block_id": block["block_id"],
                    "source_text": block["text"],
                    "citation_raw": citation["raw"],
                    "reference_id": reference_id,
                    "reference": reference,
                    "candidate_evidence": candidates,
                    "availability": unavailable,
                }
            )
    return batch

