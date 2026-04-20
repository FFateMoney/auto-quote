from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from backend.common.models import StandardChunk, StandardDocumentRecord, StandardIndexManifest


def _read_json(path: Path, default: object) -> object:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


class StandardKnowledgeBaseStore:
    def __init__(self, root_dir: Path, *, debug: bool = False) -> None:
        self.root_dir = root_dir
        self.debug = debug
        self.docs_dir = root_dir / "docs"
        self.chunks_dir = root_dir / "chunks"
        self.embeddings_dir = root_dir / "embeddings"
        self.cache_dir = root_dir / "cache"
        self.debug_dir = root_dir / "debug"
        self.manifest_path = root_dir / "manifest.json"
        self.file_hashes_path = self.cache_dir / "file_hashes.json"
        self.failures_path = self.cache_dir / "failures.json"
        self.ensure_layout()

    def ensure_layout(self) -> None:
        for path in (
            self.root_dir,
            self.docs_dir,
            self.chunks_dir,
            self.embeddings_dir,
            self.cache_dir,
            self.debug_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self.save_manifest(StandardIndexManifest())
        if not self.file_hashes_path.exists():
            self.save_file_hashes({})
        if not self.failures_path.exists():
            self._save_json(self.failures_path, {})

    def reset(self) -> None:
        if self.root_dir.exists():
            shutil.rmtree(self.root_dir)
        self.ensure_layout()

    def load_manifest(self) -> StandardIndexManifest:
        payload = _read_json(self.manifest_path, {"version": 1, "documents": []})
        return StandardIndexManifest.model_validate(payload)

    def save_manifest(self, manifest: StandardIndexManifest) -> None:
        self._save_json(self.manifest_path, manifest.model_dump())

    def load_file_hashes(self) -> dict[str, str]:
        payload = _read_json(self.file_hashes_path, {})
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items()}

    def save_file_hashes(self, mapping: dict[str, str]) -> None:
        self._save_json(self.file_hashes_path, mapping)

    def load_failures(self) -> dict[str, str]:
        payload = _read_json(self.failures_path, {})
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items()}

    def mark_failure(self, path: str, reason: str) -> None:
        payload = self.load_failures()
        payload[str(path)] = str(reason)
        self._save_json(self.failures_path, payload)

    def clear_failure(self, path: str) -> None:
        payload = self.load_failures()
        if str(path) not in payload:
            return
        payload.pop(str(path), None)
        self._save_json(self.failures_path, payload)

    def save_document_record(self, record: StandardDocumentRecord) -> None:
        self._save_json(self.docs_dir / f"{record.doc_id}.json", record.model_dump())

    def save_chunks(self, doc_id: str, chunks: list[StandardChunk]) -> None:
        path = self.chunks_dir / f"{doc_id}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for chunk in chunks:
                handle.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + "\n")

    def load_chunks(self, doc_id: str) -> list[StandardChunk]:
        path = self.chunks_dir / f"{doc_id}.jsonl"
        if not path.exists():
            return []
        chunks: list[StandardChunk] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                chunks.append(StandardChunk.model_validate(json.loads(text)))
        return chunks

    def save_embeddings(self, doc_id: str, matrix: np.ndarray) -> None:
        np.save(self.embeddings_dir / f"{doc_id}.npy", matrix)

    def load_embeddings(self, doc_id: str) -> np.ndarray:
        path = self.embeddings_dir / f"{doc_id}.npy"
        if not path.exists():
            return np.zeros((0, 0), dtype=np.float32)
        return np.load(path)

    def save_debug_artifacts(
        self,
        doc_id: str,
        *,
        pdf_analysis: dict[str, object],
        page_extraction: list[dict[str, object]],
        chunks: list[StandardChunk],
        chunk_quality_report: list[dict[str, object]],
    ) -> None:
        if not self.debug:
            return
        target = self.debug_dir / doc_id
        target.mkdir(parents=True, exist_ok=True)
        self._save_json(target / "pdf_analysis.json", pdf_analysis)
        self._save_json(target / "page_extraction.json", page_extraction)
        preview = [
            {
                "chunk_id": chunk.chunk_id,
                "section_id": chunk.section_id,
                "section_title": chunk.section_title,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "chunk_type": chunk.chunk_type,
                "quality_score": chunk.quality_score,
                "quality_level": chunk.quality_level,
                "ingest_decision": chunk.ingest_decision,
                "preview": chunk.text[:500],
            }
            for chunk in chunks
        ]
        self._save_json(target / "chunk_preview.json", preview)
        self._save_json(target / "chunk_quality_report.json", chunk_quality_report)

    def delete_document(self, doc_id: str) -> None:
        for path in (
            self.docs_dir / f"{doc_id}.json",
            self.chunks_dir / f"{doc_id}.jsonl",
            self.embeddings_dir / f"{doc_id}.npy",
        ):
            if path.exists():
                path.unlink()
        debug_path = self.debug_dir / doc_id
        if debug_path.exists():
            shutil.rmtree(debug_path)

    def _save_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
