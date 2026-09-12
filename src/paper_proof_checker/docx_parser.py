"""DOCX只读解析：提取可见正文、表格、引用和参考文献。"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Iterator

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from .io_utils import normalize_space


REFERENCE_HEADING = re.compile(r"^(references|bibliography|参考文献)\s*$", re.I)
REFERENCE_ENTRY = re.compile(r"^\s*(?:\[)?(\d{1,4})(?:\]|[.)])?\s+(.+)$")
CITATION_GROUP = re.compile(r"[\[(]([0-9][0-9,;\s\-–—]*?)[\])]", re.I)


def has_tracked_changes(path: Path) -> bool:
    """检测修订标记；存在修订时拒绝继续，避免分析不可见旧文字。"""

    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    return b"<w:ins" in xml or b"<w:del" in xml or b"<w:moveFrom" in xml


def _iter_body_items(document: DocumentObject) -> Iterator[Paragraph | Table]:
    """按文档真实顺序遍历段落和表格。"""

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _expand_citation_group(raw: str) -> list[int]:
    """把“12, 14-16”展开为编号列表，并限制异常超长范围。"""

    values: set[int] = set()
    for part in re.split(r"[,;\s]+", raw.strip()):
        if not part:
            continue
        match = re.fullmatch(r"(\d{1,4})\s*[-–—]\s*(\d{1,4})", part)
        if match:
            start, end = map(int, match.groups())
            if start <= end and end - start <= 100:
                values.update(range(start, end + 1))
        elif part.isdigit():
            values.add(int(part))
    return sorted(values)


def extract_citations(text: str) -> list[dict]:
    """提取带括号的Vancouver顺序编码引用。"""

    citations = []
    for match in CITATION_GROUP.finditer(text):
        reference_ids = _expand_citation_group(match.group(1))
        if reference_ids:
            citations.append(
                {
                    "raw": match.group(0),
                    "reference_ids": reference_ids,
                    "start": match.start(),
                    "end": match.end(),
                }
            )
    return citations


def _paragraph_kind(paragraph: Paragraph) -> str:
    """依据样式名和文字前缀识别标题、表注、图注等常见块。

    表格题注与图片题注都可能是Caption样式，因此先按文字前缀区分，
    再退回样式名，避免把表格来源误报成图注来源。
    """

    text = normalize_space(paragraph.text)
    style_name = (paragraph.style.name if paragraph.style else "").lower()
    if style_name.startswith("heading") or style_name.startswith("标题"):
        return "heading"
    if re.match(r"^(table|表)\s*\w+", text, re.I):
        return "table_caption"
    if re.match(r"^(figure|fig\.|图)\s*\w+", text, re.I):
        return "figure_caption"
    if style_name.startswith("caption") or style_name.startswith("题注"):
        return "figure_caption"
    if re.match(r"^(note|notes|注)\s*[:：]", text, re.I):
        return "table_note"
    return "paragraph"


def parse_docx(path: Path, document_name: str, require_vancouver: bool = True) -> dict:
    """把DOCX解析成稳定文档块，并提取引用和编号参考文献。

    require_vancouver=False 时允许主文没有编号参考文献与方括号引用，
    供"只检查数值"的模式使用。
    """

    if path.suffix.lower() != ".docx":
        raise ValueError(f"仅支持DOCX主文：{path}")
    if has_tracked_changes(path):
        raise ValueError(f"检测到未处理的修订痕迹，请先接受或拒绝修订：{path}")

    document = Document(path)
    blocks: list[dict] = []
    citations: list[dict] = []
    references: list[dict] = []
    current_heading = ""
    in_references = False
    paragraph_index = 0
    table_index = 0

    for item in _iter_body_items(document):
        if isinstance(item, Paragraph):
            text = normalize_space(item.text)
            if not text:
                continue
            paragraph_index += 1
            kind = _paragraph_kind(item)
            # 参考文献标题常被作者手工设为普通样式，不能只依赖Heading样式。
            if REFERENCE_HEADING.fullmatch(text):
                kind = "heading"
            if kind == "heading":
                current_heading = text
                if REFERENCE_HEADING.fullmatch(text):
                    in_references = True
            block_id = f"{document_name}-p-{paragraph_index:04d}"
            block = {
                "block_id": block_id,
                "document": document_name,
                "section": current_heading,
                "kind": kind,
                "text": text,
                "location": {
                    "heading": current_heading,
                    "paragraph_index": paragraph_index,
                },
            }
            blocks.append(block)

            if in_references and kind != "heading":
                match = REFERENCE_ENTRY.match(text)
                if match:
                    references.append(
                        {
                            "reference_id": int(match.group(1)),
                            "raw_entry": match.group(2).strip(),
                            "source_block_id": block_id,
                        }
                    )
                continue

            for citation in extract_citations(text):
                citations.append({"source_block_id": block_id, **citation})
        else:
            table_index += 1
            header_texts: list[str] = []
            for row_index, row in enumerate(item.rows, start=1):
                # 直接遍历XML行下的w:tc，天然每个真实单元格只出现一次。
                # 不能用id(cell._tc)去重：lxml元素代理会被回收，id可能被复用，
                # 从而把不同单元格误判成同一个，导致数值来源整块丢失。
                cells = [_Cell(tc, item) for tc in row._tr.findall(qn("w:tc"))]
                cell_texts = [normalize_space(cell.text) for cell in cells]
                row_text = normalize_space(" | ".join(cell_texts))
                if row_index == 1:
                    header_texts = cell_texts
                for column_index, text in enumerate(cell_texts, start=1):
                    if not text:
                        continue
                    block_id = (
                        f"{document_name}-t-{table_index:03d}"
                        f"-r-{row_index:03d}-c-{column_index:03d}"
                    )
                    blocks.append(
                        {
                            "block_id": block_id,
                            "document": document_name,
                            "section": current_heading,
                            "kind": "table_cell",
                            "text": text,
                            "context_text": row_text,
                            # 首行作为列标题，供统计指标类型推断使用。
                            "column_header": (
                                header_texts[column_index - 1]
                                if column_index - 1 < len(header_texts)
                                else ""
                            ),
                            "location": {
                                "heading": current_heading,
                                "table_index": table_index,
                                "row": row_index,
                                "column": column_index,
                            },
                        }
                    )

    if require_vancouver and document_name == "manuscript":
        if not references:
            raise ValueError("未找到可解析的编号参考文献列表，请确认存在References标题和编号条目。")
        if not citations:
            raise ValueError("未找到Vancouver顺序编码引用，如[12]或[12–15]。")

    return {
        "source_path": str(path.resolve()),
        "document": document_name,
        "blocks": blocks,
        "citations": citations,
        "references": references,
    }
