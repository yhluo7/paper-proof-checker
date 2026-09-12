"""使用pypdf和标准库生成带文本层的合成PDF，供测试与公开Demo复用。

不引入ReportLab等新依赖。段落之间保留明显垂直间距，
使pypdf的layout提取模式能够还原出段落分隔。
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 72
FONT_SIZE = 11
LEADING = 15
# 段落之间的额外间距，取两倍行距，确保layout模式能还原空行。
PARAGRAPH_GAP = LEADING * 2
WRAP_WIDTH = 88


def _escape(text: str) -> str:
    """转义PDF字符串中的括号与反斜杠。"""

    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _wrap(text: str, width: int = WRAP_WIDTH) -> list[str]:
    """按单词边界折行，超长单词直接截断。"""

    lines: list[str] = []
    current = ""
    for word in text.split():
        if len(word) > width:
            if current:
                lines.append(current)
                current = ""
            for index in range(0, len(word), width):
                lines.append(word[index : index + width])
            continue
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _font_resource(writer: PdfWriter) -> DictionaryObject:
    """构造Helvetica标准字体资源。"""

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    return DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )


def _content_stream(paragraphs: list[str]) -> DecodedStreamObject:
    """把段落列表渲染成一页的内容流，段落之间留出空白行距离。"""

    parts = ["BT", f"/F1 {FONT_SIZE} Tf", f"{LEADING} TL"]
    y = PAGE_HEIGHT - MARGIN
    for paragraph in paragraphs:
        for line in _wrap(paragraph):
            parts.append(f"1 0 0 1 {MARGIN} {y} Tm")
            parts.append(f"({_escape(line)}) Tj")
            y -= LEADING
        y -= PARAGRAPH_GAP
    parts.append("ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(parts).encode("latin-1"))
    return stream


def _paginate(paragraphs: list[str]) -> list[list[str]]:
    """按可用高度把段落分页，保证一页不会被裁掉。"""

    usable = PAGE_HEIGHT - 2 * MARGIN
    pages: list[list[str]] = []
    current: list[str] = []
    used = 0
    for paragraph in paragraphs:
        height = len(_wrap(paragraph)) * LEADING + PARAGRAPH_GAP
        if current and used + height > usable:
            pages.append(current)
            current = []
            used = 0
        current.append(paragraph)
        used += height
    if current:
        pages.append(current)
    return pages or [[]]


def build_text_pdf(
    path: Path,
    paragraphs: list[str],
    title: str | None = None,
    author: str | None = None,
    password: str | None = None,
) -> Path:
    """生成一个多页文本型PDF，可选加密，返回写入路径。"""

    writer = PdfWriter()
    for page_paragraphs in _paginate(paragraphs):
        page = writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        page[NameObject("/Resources")] = _font_resource(writer)
        page[NameObject("/Contents")] = writer._add_object(_content_stream(page_paragraphs))
    metadata = {}
    if title:
        metadata["/Title"] = title
    if author:
        metadata["/Author"] = author
    if metadata:
        writer.add_metadata(metadata)
    if password:
        writer.encrypt(user_password=password)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        writer.write(stream)
    return path


def build_blank_pdf(path: Path) -> Path:
    """生成没有文本层的PDF，用于模拟扫描件。"""

    writer = PdfWriter()
    writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        writer.write(stream)
    return path


def build_corrupt_pdf(path: Path) -> Path:
    """生成结构损坏的PDF字节流。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\ntruncated")
    return path
