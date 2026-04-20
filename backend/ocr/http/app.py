from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.ocr.http.routes import router


app = FastAPI(title="OCR Service", version="2.0.0", description="PP-StructureV3 OCR — PDF/image to Markdown")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
