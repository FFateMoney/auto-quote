from __future__ import annotations

import hashlib
import logging
import shutil
import time
from pathlib import Path

from backend.cleaning.models import BatchReport
from backend.cleaning.service import CleaningService
from backend.cleaning.settings import CleaningSettings, get_settings
from backend.common.pipeline_state import PipelineStateStore, migrate_cleaning_manifest

logger = logging.getLogger(__name__)


class CleaningLibrary:
    """批量清洗管理器：扫描 OCR 产出目录，执行清洗并输出。"""

    def __init__(self, settings: CleaningSettings | None = None) -> None:
        self._settings = settings or get_settings()
        self._service = CleaningService(self._settings)
        self._input_dir = self._settings.input_dir
        self._output_dir = self._settings.output_dir
        self._state_store = PipelineStateStore(
            stage="cleaning",
            input_root=self._input_dir,
            output_root=self._output_dir,
            state_root=self._output_dir,
            legacy_migrator=migrate_cleaning_manifest,
            legacy_filenames=("cleaning_hashes.json",),
            log=logger,
        )

    def sync(self) -> BatchReport:
        """增量清洗：跳过哈希值未发生变化的原始文件。"""
        return self._run(rebuild=False)

    def rebuild(self) -> BatchReport:
        """全量重建：清空输出目录并重新清洗所有文件。"""
        return self._run(rebuild=True)

    def _run(self, *, rebuild: bool) -> BatchReport:
        mode = "rebuild" if rebuild else "sync"
        started = time.perf_counter()

        if not self._input_dir.exists():
            logger.warning("input_dir_not_found: %s", self._input_dir)
            return BatchReport(mode=mode)

        if rebuild and self._output_dir.exists():
            for item in self._output_dir.iterdir():
                if item.name == self._state_store.state_dir.name:
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

        self._output_dir.mkdir(parents=True, exist_ok=True)

        input_files = sorted(self._input_dir.rglob("*.md"))
        report = BatchReport(mode=mode, total_found=len(input_files))

        with self._state_store.locked():
            manifest = self._state_store.empty_manifest() if rebuild else self._state_store.load()
            current_keys = {str(path.relative_to(self._input_dir)) for path in input_files}

            for path_key in sorted(set(manifest.records) - current_keys):
                record = manifest.records.pop(path_key)
                for rel_out in record.output_relpaths:
                    out_path = self._output_dir / rel_out
                    out_path.unlink(missing_ok=True)
                    self._prune_empty_parents(out_path.parent)
                self._state_store.save(manifest)

            self._remove_orphan_outputs(current_keys)

            for path in input_files:
                rel_path = path.relative_to(self._input_dir)
                path_key = str(rel_path)
                current_hash = self._compute_hash(path)
                out_path = self._output_dir / rel_path
                record = manifest.records.get(path_key)

                if record is not None and record.source_hash == current_hash and out_path.exists():
                    report.skipped += 1
                    continue

                try:
                    logger.info("cleaning | processing: %s", rel_path)
                    result = self._service.clean_file(path)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(result.cleaned_content, encoding="utf-8")
                    manifest.upsert_record(path_key, source_hash=current_hash, output_relpaths=[path_key], sink_ref=None)
                    self._state_store.save(manifest)
                    report.processed += 1
                except Exception as exc:
                    reason = f"{type(exc).__name__}: {exc}"
                    logger.error("cleaning | failed: %s | reason: %s", rel_path, reason)
                    report.failures.append(f"{rel_path}: {reason}")
                    report.failed += 1

        report.elapsed_ms = (time.perf_counter() - started) * 1000
        return report

    def _compute_hash(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _prune_empty_parents(self, path: Path) -> None:
        current = path
        while current != self._output_dir and current.exists():
            try:
                current.rmdir()
            except OSError:
                break
            current = current.parent

    def _remove_orphan_outputs(self, live_relpaths: set[str]) -> None:
        for path in self._output_dir.rglob("*.md"):
            if self._state_store.state_dir in path.parents:
                continue
            rel_path = str(path.relative_to(self._output_dir))
            if rel_path in live_relpaths:
                continue
            path.unlink(missing_ok=True)
            self._prune_empty_parents(path.parent)
