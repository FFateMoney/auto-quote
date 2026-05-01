from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from backend.quote.models import ResumeRequest, UploadedDocument
from backend.quote.orchestrator import QuoteOrchestrator
from backend.quote.settings import get_settings


logger = logging.getLogger(__name__)
router = APIRouter()
_orchestrator: QuoteOrchestrator | None = None


def get_orchestrator() -> QuoteOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = QuoteOrchestrator()
    return _orchestrator


def _sanitize_run_label(value: str) -> str:
    text = Path(value or "").stem.strip()
    if not text:
        return "run"
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._")
    return text or "run"


def _build_run_id(first_file_name: str) -> str:
    settings = get_settings()
    base = _sanitize_run_label(first_file_name)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    candidate = f"{base}_{timestamp}"
    run_root = settings.run_dir
    if not (run_root / candidate).exists():
        return candidate
    suffix = 2
    while True:
        numbered = f"{candidate}_{suffix:02d}"
        if not (run_root / numbered).exists():
            return numbered
        suffix += 1


@router.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/catalog/test-types")
def list_test_types() -> dict[str, object]:
    orchestrator = get_orchestrator()
    items = [
        {
            "id": record.id,
            "name": record.name,
            "aliases": list(record.aliases),
            "pricing_mode": record.pricing_mode,
        }
        for record in orchestrator.catalog.test_types
    ]
    return {
        "items": items,
        "load_error": orchestrator.catalog.load_error,
    }


@router.post("/api/runs")
async def create_run(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="missing_files")

    settings = get_settings()
    run_id = _build_run_id(files[0].filename or "")
    run_dir = settings.run_dir / run_id
    uploaded_dir = run_dir / "uploaded"
    uploaded_dir.mkdir(parents=True, exist_ok=True)
    uploaded_documents: list[UploadedDocument] = []
    for index, file in enumerate(files, start=1):
        safe_name = Path(file.filename or f"upload-{index}").name
        stored_name = f"{index:02d}_{safe_name}"
        stored_path = uploaded_dir / stored_name
        stored_path.write_bytes(await file.read())
        uploaded_documents.append(
            UploadedDocument(
                document_id=f"upload-{index}",
                file_name=safe_name,
                media_type=file.content_type or "",
                stored_path=str(Path("uploaded") / stored_name),
                local_path=str(stored_path),
            )
        )
    return get_orchestrator().run(run_id=run_id, uploaded_documents=uploaded_documents).model_dump()


@router.get("/api/runs/{run_id}")
def get_run(run_id: str):
    try:
        return get_orchestrator().load_run(run_id).model_dump()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc


@router.post("/api/runs/{run_id}/resume")
def resume_run(run_id: str, request: ResumeRequest):
    try:
        return get_orchestrator().resume(run_id=run_id, request=request).model_dump()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc


@router.get("/api/runs/{run_id}/artifacts/{artifact_path:path}")
def download_artifact(run_id: str, artifact_path: str):
    settings = get_settings()
    run_dir = (settings.run_dir / run_id).resolve()
    candidate = (run_dir / artifact_path).resolve()
    if run_dir not in candidate.parents and candidate != run_dir:
        raise HTTPException(status_code=400, detail="invalid_artifact_path")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return FileResponse(candidate)
