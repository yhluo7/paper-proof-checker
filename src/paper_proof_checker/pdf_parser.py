"""使用pypdf逐个PDF提取带页码和段落的文本，不执行OCR或解析嵌入对象。

设计目标：
1. 每页优先使用layout模式提取，保留版面分隔；失败时回退普通文本模式。
2. 按空行切分段落，过长段落再按句子窗口切分，避免把整页一次性交给模型。
3. 保留真实PDF页码、稳定的paragraph_id、章节标题推断以及DOI、PMID提取。
4. 加密、损坏和无文本层的PDF统一返回 parse_failed，不得被当作"证据不足"。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from pypdf import PdfReader

from .io_utils import normalize_space


# pypdf对损坏文件会输出"EOF marker not found"等告警，而本模块已用
# parse_failed状态表达同一事实，因此只保留真正的错误日志，避免CLI噪声。
logging.getLogger("pypdf").setLevel(logging.ERROR)


DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
PMID_PATTERN = re.compile(r"PMID\s*[:：]?\s*(\d{6,9})", re.I)

# 单段落字符上限，以及超过上限时每个句子窗口包含的句子数。
MAX_PARAGRAPH_CHARS = 1200
SENTENCES_PER_WINDOW = 3

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(])")
_BLANK_LINE = re.compile(r"\n[ \t]*\n+")
_SECTION_MAX_CHARS = 80
_SECTION_PUNCTUATION = re.compile(r"[.!?。！？]")


def _extract_page_text(page) -> tuple[str, str]:
    """提取一页文本，返回(文本, 使用的模式)。

    layout模式能保留表格与段落间的垂直间距，是首选；
    任何异常都退回到普通模式，避免个别页面导致整篇PDF解析失败。
    """

    try:
        layout_text = page.extract_text(extraction_mode="layout") or ""
        if layout_text.strip():
            return layout_text, "layout"
    except Exception:
        pass
    try:
        return page.extract_text() or "", "plain"
    except Exception:
        return "", "plain"


def _split_sentences(text: str) -> list[str]:
    """按句末标点切分句子，保留原文标点。"""

    parts = [part.strip() for part in _SENTENCE_BOUNDARY.split(text) if part.strip()]
    return parts or [text.strip()]


def _split_long_paragraph(text: str) -> list[str]:
    """把过长段落切成语义连续的句子窗口，避免整页进入一次推理。"""

    if len(text) <= MAX_PARAGRAPH_CHARS:
        return [text]
    windows: list[str] = []
    current: list[str] = []
    current_length = 0
    for sentence in _split_sentences(text):
        projected = current_length + len(sentence) + 1
        if current and (len(current) >= SENTENCES_PER_WINDOW or projected > MAX_PARAGRAPH_CHARS):
            windows.append(" ".join(current))
            current = []
            current_length = 0
        current.append(sentence)
        current_length += len(sentence) + 1
    if current:
        windows.append(" ".join(current))
    return windows


def _page_paragraph_texts(page_text: str) -> list[str]:
    """按空行切分段落，再对超长段落做句子窗口切分。"""

    normalized = page_text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []
    for chunk in _BLANK_LINE.split(normalized):
        collapsed = normalize_space(chunk)
        if not collapsed:
            continue
        paragraphs.extend(_split_long_paragraph(collapsed))
    return paragraphs


def _is_section_heading(text: str) -> bool:
    """很短且没有句末标点的独立段落，视为章节标题，仅用于检索加权。"""

    return len(text) <= _SECTION_MAX_CHARS and not _SECTION_PUNCTUATION.search(text)


def parse_pdf(path: Path) -> dict:
    """解析一个文本型PDF；失败时返回结构化状态而不是吞掉错误。"""

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            # 空口令能解开的PDF仍然可用；解不开的按加密处理。
            try:
                if reader.decrypt("") == 0:
                    return {"status": "parse_failed", "error": "PDF已加密", "pages": []}
            except Exception:
                return {"status": "parse_failed", "error": "PDF已加密", "pages": []}

        pages = []
        all_text_parts: list[str] = []
        current_section = ""
        for page_number, page in enumerate(reader.pages, start=1):
            page_text, _mode = _extract_page_text(page)
            paragraphs = []
            for block_number, text in enumerate(_page_paragraph_texts(page_text), start=1):
                # 章节标题只影响后续段落的检索加权，本身也作为可检索段落保留。
                if _is_section_heading(text):
                    current_section = text
                paragraphs.append(
                    {
                        "paragraph_id": f"p{page_number:04d}-b{block_number:03d}",
                        "page": page_number,
                        "section": current_section,
                        "text": text,
                    }
                )
                all_text_parts.append(text)
            pages.append({"page": page_number, "paragraphs": paragraphs})

        full_text = "\n".join(all_text_parts)
        if not full_text.strip():
            return {
                "status": "parse_failed",
                "error": "PDF没有可提取文本，可能是扫描件",
                "pages": [],
            }

        metadata = reader.metadata or {}
        title = normalize_space(str(metadata.get("/Title") or ""))
        author = normalize_space(str(metadata.get("/Author") or ""))
        first_page_text = (
            " ".join(paragraph["text"] for paragraph in pages[0]["paragraphs"][:5]) if pages else ""
        )
        if not title or title.lower() in {"untitled", "microsoft word"}:
            title = first_page_text[:300]
        doi_match = DOI_PATTERN.search(full_text)
        pmid_match = PMID_PATTERN.search(full_text)
        return {
            "status": "parsed",
            "error": None,
            "metadata": {
                "title": title,
                "author": author,
                "doi": doi_match.group(0).rstrip(".,;)") if doi_match else None,
                "pmid": pmid_match.group(1) if pmid_match else None,
                "page_count": len(pages),
            },
            "pages": pages,
        }
    except Exception as exc:  # pypdf对损坏文件可能抛出多种异常。
        return {"status": "parse_failed", "error": str(exc), "pages": []}
