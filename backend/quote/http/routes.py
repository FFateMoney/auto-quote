from __future__ import annotations

import logging
import re
import tempfile
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


@router.post("/api/runs")
async def create_run(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="missing_files")

    run_id = _build_run_id(files[0].filename or "")
    uploaded_documents: list[UploadedDocument] = []
    with tempfile.TemporaryDirectory(prefix="auto_quote_upload_") as temp_dir:
        temp_root = Path(temp_dir)
        for index, file in enumerate(files, start=1):
            safe_name = Path(file.filename or f"upload-{index}").name
            temp_path = temp_root / f"{index:02d}_{safe_name}"
            temp_path.write_bytes(await file.read())
            uploaded_documents.append(
                UploadedDocument(
                    document_id=f"upload-{index}",
                    file_name=safe_name,
                    media_type=file.content_type or "",
                    stored_path=safe_name,
                    local_path=str(temp_path),
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
