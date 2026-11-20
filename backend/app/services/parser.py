"""文档解析：PDF / DOCX / TXT / Markdown，统一输出全文与页码区间。"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedDocument:
    full_text: str
    pages: list[tuple[int, int, int]] = field(default_factory=list)  # (页码, 起始, 结束)
    page_count: int = 0

    def page_at(self, offset: int) -> int:
        for page_no, start, end in self.pages:
            if start <= offset < end:
                return page_no
        return self.pages[-1][0] if self.pages else 1


def _clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    # 合并连续空行
    out: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if not blank:
                out.append("")
            blank = True
        else:
            out.append(line)
            blank = False
    return "\n".join(out).strip()


def _build(parts: list[str]) -> ParsedDocument:
    """parts 为按页文本；用双换行分隔并记录页区间。"""
    full = ""
    pages: list[tuple[int, int, int]] = []
    for idx, part in enumerate(parts, start=1):
        text = _clean(part)
        start = len(full)
        full += text
        pages.append((idx, start, len(full)))
        full += "\n\n"
    full = full.rstrip()
    # 修正最后一页结束位置
    if pages:
        pages[-1] = (pages[-1][0], pages[-1][1], len(full))
    return ParsedDocument(full_text=full, pages=pages, page_count=len(parts))


def parse_pdf(data: bytes) -> ParsedDocument:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = [(page.extract_text() or "") for page in reader.pages]
    return _build(parts)


def parse_docx(data: bytes) -> ParsedDocument:
    from docx import Document as DocxDocument

    doc = DocxDocument(io.BytesIO(data))
    blocks: list[str] = []
    for para in doc.paragraphs:
        if para.text.strip():
            style = (para.style.name or "").lower()
            if "heading" in style or style.startswith("标题"):
                blocks.append(f"# {para.text.strip()}")
            else:
                blocks.append(para.text.strip())
    for table in doc.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            rows.append(" | ".join(cells))
        if rows:
            blocks.append("\n".join(rows))
    return _build(["\n\n".join(blocks)])


def parse_text(data: bytes) -> ParsedDocument:
    for encoding in ("utf-8", "gb18030", "utf-16"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="ignore")
    return _build([text])


def parse_file(path: Path, filename: str) -> ParsedDocument:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    data = path.read_bytes()
    if suffix == "pdf":
        return parse_pdf(data)
    if suffix in ("docx",):
        return parse_docx(data)
    if suffix in ("txt", "md", "markdown"):
        return parse_text(data)
    if suffix == "doc":
        raise ValueError("暂不支持 .doc 旧格式，请另存为 .docx 后上传")
    raise ValueError(f"暂不支持的文件类型：.{suffix}")
