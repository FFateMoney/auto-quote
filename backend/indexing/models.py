from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any


class StandardMetadata(BaseModel):
    standard_id: str = Field(..., description="规范化后的标准号, 如 gbt24231")
    file_name: str = Field(..., description="原始文件名")
    heading_path: list[str] = Field(default_factory=list, description="标题层级路径")
    page_num: int | None = Field(None, description="页码(如果有)")


class StandardChunk(BaseModel):
    id: str = Field(..., description="唯一 ID (UUID)")
    text: str = Field(..., description="清洗后的段落文本")
    full_context_text: str = Field(..., description="包含标题层级路径的增强语义文本")
    metadata: StandardMetadata
    vector: list[float] | None = None
    sequence_id: int | None = Field(None, description="同一标题下的序列号（按大小切分时用）")


class IndexingReport(BaseModel):
    mode: str  # 'sync' or 'rebuild'
    total_files: int = 0
    processed_files: int = 0
    total_chunks: int = 0
    failed_files: int = 0
    failures: list[str] = Field(default_factory=list)
    elapsed_ms: float = 0.0


class SearchQuery(BaseModel):
    query: str
    filters: dict[str, Any] | None = None
    top_k: int = 5


class SearchResult(BaseModel):
    text: str
    score: float
    metadata: StandardMetadata
