"""文本切片：按标题分节、定长聚合，保留页码与字符偏移用于原文定位。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import CHUNK_OVERLAP, CHUNK_SIZE
from .parser import ParsedDocument

HEADING_RE = re.compile(
    r"^(?:#{1,6}\s+.+"                     # markdown
    r"|第[一二三四五六七八九十百零〇\d]+[章节条]\s*.+"
    r"|[一二三四五六七八九十]+、.+"
    r"|\d+(?:\.\d+){0,3}[、.．]\s*\S.+"
    r"|（[一二三四五六七八九十]+）.+)$"
)
HEADING_MAX_LEN = 32
SENTENCE_SPLIT = re.compile(r"(?<=[。！？；!?;])\s*")


def _heading_level(text: str) -> int:
    if text.startswith("#"):
        return max(0, len(text) - len(text.lstrip("#")) - 1)
    if re.match(r"^第[一二三四五六七八九十百零〇\d]+[章节]", text):
        return 1
    if re.match(r"^[一二三四五六七八九十]+、", text):
        return 1
    if re.match(r"^（[一二三四五六七八九十]+）", text):
        return 2
    return 2


def _is_heading(text: str) -> bool:
    if len(text) > HEADING_MAX_LEN:
        return False
    if text.endswith(("。", "；", ";", "，", ",")):
        return False
    if "：" in text or ":" in text:
        return text.startswith("#")
    return bool(HEADING_RE.match(text))


@dataclass
class ChunkData:
    content: str
    page: int
    section: str
    start_char: int
    end_char: int

    @property
    def token_count(self) -> int:
        return max(1, int(len(self.content) * 0.75))


def _blocks(text: str) -> list[tuple[str, int, int]]:
    """按空行与标题行切块，并记录绝对字符偏移。"""
    result: list[tuple[str, int, int]] = []
    pos = 0
    buf: list[str] = []
    buf_start = 0

    def flush(end: int) -> None:
        nonlocal buf
        if buf:
            result.append(("\n".join(buf), buf_start, end))
            buf = []

    for line in text.split("\n"):
        line_start = pos
        pos += len(line) + 1
        stripped = line.strip()
        if not stripped:
            flush(line_start)
            continue
        if _is_heading(stripped):
            flush(line_start)
            result.append((stripped, line_start, line_start + len(line)))
            continue
        if not buf:
            buf_start = line_start
        buf.append(line)
    flush(len(text))
    return result


def _split_long(text: str, start: int) -> list[tuple[str, int, int]]:
    """超长段落按句切分，句间保留少量重叠。"""
    pieces: list[tuple[str, int, int]] = []
    cursor = 0
    sentences = [s for s in SENTENCE_SPLIT.split(text) if s]
    buf = ""
    buf_start = start
    for sentence in sentences:
        if buf and len(buf) + len(sentence) > CHUNK_SIZE:
            pieces.append((buf, buf_start, buf_start + len(buf)))
            overlap = buf[-CHUNK_OVERLAP:] if CHUNK_OVERLAP else ""
            buf_start = buf_start + len(buf) - len(overlap)
            buf = overlap + sentence
        else:
            buf += sentence
        cursor += len(sentence)
    if buf.strip():
        pieces.append((buf, buf_start, buf_start + len(buf)))
    return pieces


def chunk_document(doc: ParsedDocument) -> list[ChunkData]:
    blocks: list[tuple[str, int, int]] = []
    for text, start, end in _blocks(doc.full_text):
        if len(text) > CHUNK_SIZE * 1.6:
            blocks.extend(_split_long(text, start))
        else:
            blocks.append((text, start, end))

    chunks: list[ChunkData] = []
    buf: list[str] = []
    buf_len = 0
    buf_start = 0
    buf_end = 0
    section = ""
    section_titles: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal buf, buf_len, buf_start, buf_end
        if not buf:
            return
        content = "\n".join(buf).strip()
        if content:
            chunks.append(
                ChunkData(
                    content=content,
                    page=doc.page_at(buf_start),
                    section=section,
                    start_char=buf_start,
                    end_char=buf_end,
                )
            )
        buf, buf_len, buf_end = [], 0, 0

    for text, start, end in blocks:
        stripped = text.strip()
        if _is_heading(stripped):
            flush()
            title = stripped.lstrip("#").strip()
            level = _heading_level(stripped)
            while section_titles and section_titles[-1][0] >= level:
                section_titles.pop()
            section_titles.append((level, title))
            section = " / ".join(item[1] for item in section_titles)
            continue
        if buf and buf_len + len(text) > CHUNK_SIZE:
            flush()
        if not buf:
            buf_start = start
        buf.append(text)
        buf_len += len(text) + 1
        buf_end = end

    flush()
    return chunks
