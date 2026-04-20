"""
Library builder: scan standards/origin/ for PDFs, OCR each one, write markdown to data/ocr_markdown/.

Supports two modes:
  sync    — incremental: skip files whose content hash hasn't changed
  rebuild — full: wipe output dir and reprocess everything
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.ocr.service import OcrService
from backend.ocr.settings import OcrSettings, get_settings


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LibraryBuildReport:
    mode: str
    total_found: int = 0
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    removed: int = 0
    failures: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


class LibraryBuilder:
    """Scan origin_dir for PDFs, OCR each one, write .md files to output_dir."""

    _CACHE_SUBDIR = ".cache"
    _HASHES_FILE = "file_hashes.json"
    _OUTPUTS_FILE = "outputs.json"

    def __init__(self, settings: OcrSettings | None = None) -> None:
        s = settings or get_settings()
        self._service = OcrService(s)
        self._origin_dir = s.origin_dir
        self._output_dir = s.output_dir
        self._cache_dir = self._output_dir / self._CACHE_SUBDIR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync(self) -> LibraryBuildReport:
        """Incremental build — skip PDFs whose SHA-256 hash hasn't changed."""
        return self._run(rebuild=False)

    def rebuild(self) -> LibraryBuildReport:
        """Full rebuild — wipe output_dir and reprocess everything."""
        return self._run(rebuild=True)

    def status(self) -> dict[str, object]:
        """Return a snapshot of the current library state."""
        hashes = self._read_json(self._cache_dir / self._HASHES_FILE, {})
        outputs = self._read_json(self._cache_dir / self._OUTPUTS_FILE, {})
        origin_pdfs = self._scan_pdfs()
        return {
            "origin_dir": str(self._origin_dir),
            "output_dir": str(self._output_dir),
            "origin_pdf_count": len(origin_pdfs),
            "processed_count": len(outputs),
            "output_dir_exists": self._output_dir.exists(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self, *, rebuild: bool) -> LibraryBuildReport:
        mode = "rebuild" if rebuild else "sync"
        started = time.perf_counter()

        if not self._origin_dir.exists():
            raise RuntimeError(f"origin_dir_not_found:{self._origin_dir}")

        if rebuild and self._output_dir.exists():
            shutil.rmtree(self._output_dir)

        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        prev_hashes: dict[str, str] = {} if rebuild else self._read_json(self._cache_dir / self._HASHES_FILE, {})
        prev_outputs: dict[str, str] = {} if rebuild else self._read_json(self._cache_dir / self._OUTPUTS_FILE, {})

        pdf_paths = self._scan_pdfs()
        report = LibraryBuildReport(mode=mode, total_found=len(pdf_paths))

        # Build lookup of what's currently in origin
        live_keys: set[str] = {str(p) for p in pdf_paths}

        # Remove stale outputs for PDFs that no longer exist in origin
        for path_key, rel_out in list(prev_outputs.items()):
            if path_key not in live_keys:
                out_path = self._output_dir / rel_out
                out_path.unlink(missing_ok=True)
                self._prune_empty_parents(out_path.parent)
                report.removed += 1

        # Compute what needs processing
        pending: list[tuple[Path, str, str, str]] = []
        for path in pdf_paths:
            path_key = str(path)
            file_hash = self._sha256(path)
            rel_out = self._rel_output(path)
            pending.append((path, path_key, file_hash, rel_out))

        need_count = sum(1 for _, pk, fh, _ in pending if not (mode == "sync" and prev_hashes.get(pk) == fh))
        logger.info("library build | mode=%s total=%s need=%s skipped=%s", mode, len(pdf_paths), need_count, len(pdf_paths) - need_count)

        next_hashes: dict[str, str] = {}
        next_outputs: dict[str, str] = {}
        done = 0

        for path, path_key, file_hash, rel_out in pending:
            next_hashes[path_key] = file_hash
            next_outputs[path_key] = rel_out

            if mode == "sync" and prev_hashes.get(path_key) == file_hash:
                report.skipped += 1
                continue

            done += 1
            logger.info("library build | %s/%s | %s", done, need_count or 1, path.name)
            try:
                result = self._service.process_path(path)
                if not result.markdown_text.strip():
                    raise RuntimeError("empty_markdown_output")
                out_path = self._output_dir / rel_out
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(result.markdown_text, encoding="utf-8")
                report.processed += 1
            except KeyboardInterrupt:
                logger.warning("library build interrupted | file=%s", path.name)
                self._save_state(next_hashes, next_outputs)
                raise
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                logger.warning("library build failed | file=%s | reason=%s", path.name, reason)
                report.failures.append(f"{path.name}: {reason}")
                report.failed += 1
                # Don't cache failed files so next sync retries them
                next_hashes.pop(path_key, None)
                next_outputs.pop(path_key, None)
                continue

            self._save_state(next_hashes, next_outputs)

        self._save_state(next_hashes, next_outputs)
        report.elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        logger.info(
            "library build done | processed=%s skipped=%s failed=%s removed=%s elapsed_ms=%s",
            report.processed, report.skipped, report.failed, report.removed, report.elapsed_ms,
        )
        return report

    def _scan_pdfs(self) -> list[Path]:
        if not self._origin_dir.exists():
            return []
        return sorted(p for p in self._origin_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")

    def _rel_output(self, pdf_path: Path) -> str:
        return str(pdf_path.relative_to(self._origin_dir).with_suffix(".md"))

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _prune_empty_parents(self, path: Path) -> None:
        current = path
        while current != self._output_dir and current.exists():
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def _save_state(self, hashes: dict[str, str], outputs: dict[str, str]) -> None:
        self._write_json(self._cache_dir / self._HASHES_FILE, hashes)
        self._write_json(self._cache_dir / self._OUTPUTS_FILE, outputs)

    def _read_json(self, path: Path, default: dict) -> dict:
        if not path.exists():
            return dict(default)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return dict(default)
        return payload if isinstance(payload, dict) else dict(default)

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
