from __future__ import annotations

from fastapi import APIRouter, Body
from backend.cleaning.models import CleaningOptions, CleaningResult
from backend.cleaning.service import CleaningService

router = APIRouter()


@router.post("/clean", response_model=CleaningResult)
async def clean_markdown(
    content: str = Body(..., embed=True),
    options: CleaningOptions | None = Body(None)
) -> CleaningResult:
    """
    清洗指定的 Markdown 内容。
    """
    service = CleaningService(options=options)
    return service.clean_text(content)


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
