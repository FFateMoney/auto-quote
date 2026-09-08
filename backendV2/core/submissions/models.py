from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuoteValues(StrictModel):
    fixed_fields: dict[str, Any] = Field(alias="固定字段")
    special_fields: dict[str, Any] = Field(alias="专有字段")


class QuoteTable(StrictModel):
    """One independent quotation table stored under ``quotes/<quote_id>/``."""

    schema_version: Literal[1]
    test_project_id: int | None = Field(
        description="所选测试项目三元组的 ID；无法确定时为 null。"
    )
    values: QuoteValues = Field(description="按动态字段表填写的固定字段与专有字段。")


@dataclass(frozen=True, slots=True)
class QuoteTableSubmission:
    quote_id: str
    quote_table: QuoteTable
