from __future__ import annotations

from pydantic import BaseModel, Field


class CleaningOptions(BaseModel):
    fix_tables: bool = Field(default=True, description="是否修复并补全表格内容")
    remove_cid: bool = Field(default=True, description="是否剔除 (cid:xxx) 占位符")
    fix_hyphens: bool = Field(default=True, description="是否修复换行导致的连字符断词")
    normalize_whitespace: bool = Field(default=True, description="是否压缩多余空白和空行")


class CleaningStats(BaseModel):
    removed_tags: int = 0
    fixed_tables: int = 0
    removed_cids: int = 0
    fixed_hyphens: int = 0


class CleaningResult(BaseModel):
    cleaned_content: str
    stats: CleaningStats = Field(default_factory=CleaningStats)


class BatchReport(BaseModel):
    mode: str  # 'sync' or 'rebuild'
    total_found: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    failures: list[str] = Field(default_factory=list)
    elapsed_ms: float = 0.0
