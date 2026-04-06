from __future__ import annotations

import re
from dataclasses import dataclass

from packages.core.models import StandardChunk, StandardDocumentRecord


NUMERIC_SECTION_RE = re.compile(r"^(?P<section>\d+(?:\.\d+){1,4})\s+(?P<title>.+)$")
HYPHEN_SECTION_RE = re.compile(r"^(?P<section>\d+(?:-\d+){1,3})\.?\s+(?P<title>.+)$")
CODE_SECTION_RE = re.compile(r"^(?P<section>[A-Z]{1,4}/\d{2})\s+(?P<title>.+)$")
KEYWORD_RE = re.compile(
    r"高温|低温|湿热|温度循环|振动|冲击|盐雾|防尘|防水|试验|储存|工作|temperature|humidity|vibration|shock|salt|dust|water|test",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"[A-Za-z0-9_.+\-/]+|[\u4e00-\u9fff]{1,8}")
IGNORED_TITLES = {"sec", "min", "off", "on", "hz", "khz", "mhz", "s", "h"}


@dataclass(slots=True)
class _LineRef:
    page_num: int
    line_index: int
    text: str


@dataclass(slots=True)
class _HeadingRef:
    flat_index: int
    page_num: int
    section_id: str
    title: str
    depth: int


def _heading_from_line(line: str) -> tuple[str, str] | None:
    text = str(line or "").strip()
    for pattern in (NUMERIC_SECTION_RE, HYPHEN_SECTION_RE, CODE_SECTION_RE):
        match = pattern.match(text)
        if not match:
            continue
        section_id = match.group("section").strip()
        title = match.group("title").strip()
        if not title:
            continue
        if "....." in title or "·····" in title:
            continue
        if title.lower().strip(" .") in IGNORED_TITLES:
            continue
        if section_id.startswith("0."):
            continue
        if re.fullmatch(r"[\d.\-/% ]+", title):
            continue
        return section_id, title
    return None


def _section_depth(section_id: str) -> int:
    if "." in section_id:
        return section_id.count(".") + 1
    if "-" in section_id:
        return section_id.count("-") + 1
    return 1


def _parent_section_id(section_id: str) -> str:
    if "." in section_id:
        return section_id.rsplit(".", 1)[0]
    if "-" in section_id:
        return section_id.rsplit("-", 1)[0]
    return ""


def _chunk_type(section_id: str) -> str:
    return "subsection" if _section_depth(section_id) >= 4 else "section"


def _keywords(text: str, title: str) -> list[str]:
    found = {match.group(0) for match in KEYWORD_RE.finditer(f"{title}\n{text}")}
    for token in TOKEN_RE.findall(title):
        if len(token) >= 2:
            found.add(token)
    return sorted(found)[:24]


class StandardChunker:
    def chunk_document(self, doc: StandardDocumentRecord, pages: list[str]) -> list[StandardChunk]:
        line_refs: list[_LineRef] = []
        headings: list[_HeadingRef] = []
        for page_num, page in enumerate(pages, start=1):
            lines = [line.strip() for line in str(page or "").splitlines() if line.strip()]
            for line_index, line in enumerate(lines):
                flat_index = len(line_refs)
                line_refs.append(_LineRef(page_num=page_num, line_index=line_index, text=line))
                heading = _heading_from_line(line)
                if heading:
                    section_id, title = heading
                    headings.append(
                        _HeadingRef(
                            flat_index=flat_index,
                            page_num=page_num,
                            section_id=section_id,
                            title=title,
                            depth=_section_depth(section_id),
                        )
                    )

        if not headings:
            return self._fallback_chunks(doc, pages)

        chunks: list[StandardChunk] = []
        for index, heading in enumerate(headings):
            end_index = self._end_index_for_heading(index=index, headings=headings, line_refs=line_refs)
            selected_refs = line_refs[heading.flat_index:end_index]
            text = "\n".join(ref.text for ref in selected_refs).strip()
            if not text:
                continue
            chunks.append(
                StandardChunk(
                    chunk_id=f"{doc.doc_id}::{heading.section_id}",
                    doc_id=doc.doc_id,
                    standard_code=doc.standard_code,
                    path=doc.path,
                    page_start=selected_refs[0].page_num,
                    page_end=selected_refs[-1].page_num,
                    section_id=heading.section_id,
                    section_title=heading.title,
                    parent_section_id=_parent_section_id(heading.section_id),
                    chunk_type=_chunk_type(heading.section_id),
                    text=text,
                    normalized_text=text,
                    keywords=_keywords(text, heading.title),
                    aliases=[heading.title],
                )
            )
        return chunks or self._fallback_chunks(doc, pages)

    def _end_index_for_heading(
        self,
        *,
        index: int,
        headings: list[_HeadingRef],
        line_refs: list[_LineRef],
    ) -> int:
        current = headings[index]
        for follower in headings[index + 1 :]:
            if follower.depth <= current.depth:
                return follower.flat_index
        return len(line_refs)

    def _fallback_chunks(self, doc: StandardDocumentRecord, pages: list[str]) -> list[StandardChunk]:
        chunks: list[StandardChunk] = []
        for page_num, page in enumerate(pages, start=1):
            text = str(page or "").strip()
            if not text:
                continue
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            title = lines[0][:80] if lines else f"page-{page_num}"
            chunks.append(
                StandardChunk(
                    chunk_id=f"{doc.doc_id}::page-{page_num}",
                    doc_id=doc.doc_id,
                    standard_code=doc.standard_code,
                    path=doc.path,
                    page_start=page_num,
                    page_end=page_num,
                    section_id=f"page-{page_num}",
                    section_title=title,
                    chunk_type="page_fallback",
                    text=text,
                    normalized_text=text,
                    keywords=_keywords(text, title),
                    aliases=[title],
                )
            )
        return chunks
