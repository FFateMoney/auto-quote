from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.ocr.library import LibraryBuildReport, LibraryBuilder
from backend.ocr.service import OcrService


router = APIRouter()
_service = OcrService()
_builder = LibraryBuilder()


# ------------------------------------------------------------------
# Response models
# ------------------------------------------------------------------

class MarkdownResponse(BaseModel):
    request_id: str
    engine: str
    markdown_text: str = ""
    page_count: int = 0
    timings: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LibraryBuildResponse(BaseModel):
    mode: str
    total_found: int
    processed: int
    skipped: int
    failed: int
    removed: int
    failures: list[str] = Field(default_factory=list)
    elapsed_ms: float


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.get("/api/health")
def health() -> dict[str, object]:
    from backend.ocr.settings import get_settings
    s = get_settings()
    importable = True
    import_error = ""
    try:
        from paddleocr import PPStructureV3  # noqa: F401
    except Exception as exc:
        importable = False
        import_error = str(exc)
    return {
        "status": "ok",
        "engine": "pp_structurev3",
        "device": s.device,
        "origin_dir": str(s.origin_dir),
        "output_dir": str(s.output_dir),
        "pp_structurev3_importable": importable,
        "pp_structurev3_import_error": import_error,
    }


@router.post("/api/ocr/markdown", response_model=MarkdownResponse)
async def ocr_markdown(file: UploadFile = File(...)) -> MarkdownResponse:
    filename = file.filename or "upload.bin"
    try:
        payload = await file.read()
        result = _service.process_bytes(payload, filename=filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return MarkdownResponse(
        request_id=result.request_id,
        engine=result.engine,
        markdown_text=result.markdown_text,
        page_count=result.page_count,
        timings=result.timings,
        metadata=result.metadata,
    )


@router.get("/api/ocr/library/status")
def library_status() -> dict[str, object]:
    return _builder.status()


@router.post("/api/ocr/library/sync", response_model=LibraryBuildResponse)
def library_sync() -> LibraryBuildResponse:
    try:
        report = _builder.sync()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _to_build_response(report)


@router.post("/api/ocr/library/rebuild", response_model=LibraryBuildResponse)
def library_rebuild() -> LibraryBuildResponse:
    try:
        report = _builder.rebuild()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _to_build_response(report)


def _to_build_response(r: LibraryBuildReport) -> LibraryBuildResponse:
    return LibraryBuildResponse(
        mode=r.mode,
        total_found=r.total_found,
        processed=r.processed,
        skipped=r.skipped,
        failed=r.failed,
        removed=r.removed,
        failures=r.failures,
        elapsed_ms=r.elapsed_ms,
    )
