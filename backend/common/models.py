"""Cross-service shared models.

Only models consumed by more than one service live here.
Quote-specific models (FormRow, RunState, etc.) live in backend.quote.models.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Document normalisation (used by quote plugins and potentially ingest)
# ---------------------------------------------------------------------------

class DocumentAsset(BaseModel):
    asset_id: str
    asset_type: Literal["image"] = "image"
    mime_type: str
    data_url: str
    position: str = ""
    context_text: str = ""


class NormalizedTextBlock(BaseModel):
    block_id: str
    block_type: str
    text: str
    source_path: str = ""


class NormalizedDocument(BaseModel):
    document_id: str
    source_name: str
    source_kind: str
    original_path: str
    text_blocks: list[NormalizedTextBlock] = Field(default_factory=list)
    assets: list[DocumentAsset] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Standard knowledge base (used by quote flow and indexing tooling)
# ---------------------------------------------------------------------------

class StandardDocumentRecord(BaseModel):
    doc_id: str
    standard_key: str = ""
    standard_code: str = ""
    title: str = ""
    path: str
    category: str = ""
    language: str = ""
    page_count: int = 0
    file_hash: str = ""
    pdf_type: str = ""
    text_extraction_mode: str = ""
    suspected_encoding_issue: bool = False
    indexed_at: str = Field(default_factory=_now_iso)
    chunk_count: int = 0


class StandardChunk(BaseModel):
    chunk_id: str
    doc_id: str
    standard_code: str = ""
    path: str
    page_start: int = 0
    page_end: int = 0
    section_id: str = ""
    section_title: str = ""
    parent_section_id: str = ""
    chunk_type: Literal["section", "subsection", "table_row", "page_fallback"] = "section"
    text: str = ""
    normalized_text: str = ""
    keywords: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    quality_score: float | None = None
    quality_level: str = ""
    quality_reasons: list[str] = Field(default_factory=list)
    ingest_decision: str = ""
    vector_row: int | None = None


class StandardIndexManifest(BaseModel):
    version: int = 1
    updated_at: str = Field(default_factory=_now_iso)
    documents: list[StandardDocumentRecord] = Field(default_factory=list)
