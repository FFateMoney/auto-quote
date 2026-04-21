"""
Library builder: scan standards/origin/ for PDFs, OCR each one, write markdown to data/ocr_markdown/.

Supports two modes:
  sync    — incremental: skip files whose content hash hasn't changed
  rebuild — full: wipe output dir and reprocess everything
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from backend.common.pipeline_state import PipelineStateStore, migrate_ocr_manifest
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

    def __init__(self, settings: OcrSettings | None = None) -> None:
        s = settings or get_settings()
        self._service = OcrService(s)
        self._origin_dir = s.origin_dir
        self._output_dir = s.output_dir
        self._state_store = PipelineStateStore(
            stage="ocr",
            input_root=self._origin_dir,
            output_root=self._output_dir,
            state_root=self._output_dir,
            legacy_migrator=migrate_ocr_manifest,
            legacy_filenames=("file_hashes.json", "outputs.json"),
            log=logger,
        )

    def sync(self) -> LibraryBuildReport:
        """Incremental build — skip PDFs whose SHA-256 hash hasn't changed."""
        return self._run(rebuild=False)

    def rebuild(self) -> LibraryBuildReport:
        """Full rebuild — wipe output_dir and reprocess everything."""
        return self._run(rebuild=True)

    def status(self) -> dict[str, object]:
        """Return a snapshot of the current library state."""
        with self._state_store.locked():
            manifest = self._state_store.load()
        origin_pdfs = self._scan_pdfs()
        return {
            "origin_dir": str(self._origin_dir),
            "output_dir": str(self._output_dir),
            "origin_pdf_count": len(origin_pdfs),
            "processed_count": len(manifest.records),
            "output_dir_exists": self._output_dir.exists(),
        }

    def _run(self, *, rebuild: bool) -> LibraryBuildReport:
        mode = "rebuild" if rebuild else "sync"
        started = time.perf_counter()

        if not self._origin_dir.exists():
            raise RuntimeError(f"origin_dir_not_found:{self._origin_dir}")

        if rebuild and self._output_dir.exists():
            shutil.rmtree(self._output_dir)

        self._output_dir.mkdir(parents=True, exist_ok=True)

        pdf_paths = self._scan_pdfs()
        pending = [(path, self._rel_input(path), self._sha256(path), self._rel_output(path)) for path in pdf_paths]
        report = LibraryBuildReport(mode=mode, total_found=len(pending))

        with self._state_store.locked():
            manifest = self._state_store.empty_manifest() if rebuild else self._state_store.load()
            live_keys = {path_key for _, path_key, _, _ in pending}

            for path_key in sorted(set(manifest.records) - live_keys):
                record = manifest.records.pop(path_key)
                for rel_out in record.output_relpaths:
                    out_path = self._output_dir / rel_out
                    out_path.unlink(missing_ok=True)
                    self._prune_empty_parents(out_path.parent)
                report.removed += 1
                self._state_store.save(manifest)

            need_count = 0
            for _, path_key, file_hash, rel_out in pending:
                record = manifest.records.get(path_key)
                out_path = self._output_dir / rel_out
                if record is None or record.source_hash != file_hash or not out_path.exists():
                    need_count += 1

            logger.info(
                "library build | mode=%s total=%s need=%s skipped=%s",
                mode,
                len(pending),
                need_count,
                len(pending) - need_count,
            )

            done = 0
            for path, path_key, file_hash, rel_out in pending:
                record = manifest.records.get(path_key)
                out_path = self._output_dir / rel_out
                if record is not None and record.source_hash == file_hash and out_path.exists():
                    report.skipped += 1
                    continue

                done += 1
                logger.info("library build | %s/%s | %s", done, need_count or 1, path.name)
                try:
                    result = self._service.process_path(path)
                    if not result.markdown_text.strip():
                        raise RuntimeError("empty_markdown_output")
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(result.markdown_text, encoding="utf-8")
                    manifest.upsert_record(path_key, source_hash=file_hash, output_relpaths=[rel_out], sink_ref=None)
                    self._state_store.save(manifest)
                    report.processed += 1
                except KeyboardInterrupt:
                    logger.warning("library build interrupted | file=%s", path.name)
                    raise
                except Exception as exc:
                    reason = f"{type(exc).__name__}: {exc}"
                    logger.warning("library build failed | file=%s | reason=%s", path.name, reason)
                    report.failures.append(f"{path.name}: {reason}")
                    report.failed += 1

        report.elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        logger.info(
            "library build done | processed=%s skipped=%s failed=%s removed=%s elapsed_ms=%s",
            report.processed,
            report.skipped,
            report.failed,
            report.removed,
            report.elapsed_ms,
        )
        return report

    def _scan_pdfs(self) -> list[Path]:
        if not self._origin_dir.exists():
            return []
        return sorted(p for p in self._origin_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")

    def _rel_input(self, pdf_path: Path) -> str:
        return str(pdf_path.relative_to(self._origin_dir))

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
