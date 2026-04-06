from __future__ import annotations

import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from packages.core.logging_utils import setup_logging
from packages.core.models import ResumeRequest, UploadedDocument
from packages.core.orchestrator import QuoteOrchestrator
from packages.integrations.settings import get_settings


setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Auto Quote API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = QuoteOrchestrator()


def _sanitize_run_label(value: str) -> str:
    text = Path(value or "").stem.strip()
    if not text:
        return "run"
    text = re.sub(r"[\\/:*?\"<>|]+", "_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._")
    return text or "run"


def _build_run_id(settings: object, first_file_name: str) -> str:
    base = _sanitize_run_label(first_file_name)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    candidate = f"{base}_{timestamp}"
    run_root = Path(str(settings.run_dir))
    if not (run_root / candidate).exists():
        return candidate

    suffix = 2
    while True:
        numbered = f"{candidate}_{suffix:02d}"
        if not (run_root / numbered).exists():
            return numbered
        suffix += 1


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/runs")
async def create_run(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="missing_files")

    settings = get_settings()
    run_id = _build_run_id(settings, files[0].filename or "")
    logger.info("API 收到上传请求: run=%s files=%s", run_id, len(files))
    uploaded_documents: list[UploadedDocument] = []
    with tempfile.TemporaryDirectory(prefix="auto_quote_upload_") as temp_dir:
        temp_root = Path(temp_dir)
        for index, file in enumerate(files, start=1):
            safe_name = Path(file.filename or f"upload-{index}").name
            temp_path = temp_root / f"{index:02d}_{safe_name}"
            content = await file.read()
            temp_path.write_bytes(content)
            uploaded_documents.append(
                UploadedDocument(
                    document_id=f"upload-{index}",
                    file_name=safe_name,
                    media_type=file.content_type or "",
                    stored_path=safe_name,
                    local_path=str(temp_path),
                )
            )

        state = orchestrator.run(run_id=run_id, uploaded_documents=uploaded_documents)
    logger.info("API 运行结束: run=%s status=%s stage=%s", run_id, state.overall_status, state.current_stage)
    return state.model_dump()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    try:
        state = orchestrator.load_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc
    return state.model_dump()


@app.post("/api/runs/{run_id}/resume")
def resume_run(run_id: str, request: ResumeRequest):
    try:
        logger.info("API 收到继续报价请求: run=%s row=%s", run_id, request.row_id)
        state = orchestrator.resume(run_id=run_id, request=request)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run_not_found") from exc
    logger.info("API 继续报价结束: run=%s status=%s stage=%s", run_id, state.overall_status, state.current_stage)
    return state.model_dump()


@app.get("/api/runs/{run_id}/artifacts/{artifact_path:path}")
def download_artifact(run_id: str, artifact_path: str):
    settings = get_settings()
    run_dir = (settings.run_dir / run_id).resolve()
    candidate = (run_dir / artifact_path).resolve()
    if run_dir not in candidate.parents and candidate != run_dir:
        raise HTTPException(status_code=400, detail="invalid_artifact_path")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="artifact_not_found")
    return FileResponse(candidate)
