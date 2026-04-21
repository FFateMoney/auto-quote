from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from backend.common.pipeline_state import PipelineStateStore, migrate_indexing_manifest
from backend.indexing.engine import Qwen3EmbeddingEngine
from backend.indexing.models import IndexingReport
from backend.indexing.service import IndexingService
from backend.indexing.settings import IndexingSettings, get_settings

logger = logging.getLogger(__name__)


class IndexingLibrary:
    """批量索引管理器：扫描清洗后的 MD 目录，构建向量索引。"""

    def __init__(self, settings: IndexingSettings | None = None) -> None:
        self._settings = settings or get_settings()
        self._input_dir = self._settings.input_dir
        self._service: IndexingService | None = None
        self._state_store = PipelineStateStore(
            stage="indexing",
            input_root=self._input_dir,
            output_root=None,
            state_root=self._input_dir,
            legacy_migrator=migrate_indexing_manifest,
            legacy_filenames=("indexing_hashes.json",),
            log=logger,
        )

    def sync(self) -> IndexingReport:
        return self._run(rebuild=False)

    def rebuild(self) -> IndexingReport:
        return self._run(rebuild=True)

    def _run(self, *, rebuild: bool) -> IndexingReport:
        mode = "rebuild" if rebuild else "sync"
        started = time.perf_counter()

        if not self._input_dir.exists():
            return IndexingReport(mode=mode)

        input_files = sorted(self._input_dir.rglob("*.md"))
        engine = Qwen3EmbeddingEngine() if input_files else None
        self._service = IndexingService(engine=engine)

        if rebuild:
            self._service.reset_all()

        report = IndexingReport(mode=mode, total_files=len(input_files))

        with self._state_store.locked():
            manifest = self._state_store.empty_manifest() if rebuild else self._state_store.load()
            if not rebuild and manifest.records and not self._service._store.has_points():
                logger.warning("indexing | empty collection detected, clearing local sync state")
                manifest = self._state_store.empty_manifest()
                self._state_store.save(manifest)

            current_file_keys = {str(path.relative_to(self._input_dir)) for path in input_files}
            for deleted_key in sorted(set(manifest.records) - current_file_keys):
                logger.info("indexing | cleaning deleted file: %s", deleted_key)
                self._service._store.delete_by_source_key(deleted_key)
                manifest.records.pop(deleted_key, None)
                self._state_store.save(manifest)

            for path in input_files:
                source_key = str(path.relative_to(self._input_dir))
                file_name = path.name
                current_hash = self._compute_hash(path)
                record = manifest.records.get(source_key)

                if not rebuild and record is not None and record.source_hash == current_hash:
                    report.processed_files += 1
                    continue

                try:
                    logger.info("indexing | processing: %s", source_key)
                    content = path.read_text(encoding="utf-8")
                    standard_id = path.stem
                    count = self._service.index_file(content, file_name, standard_id, source_key)
                    report.total_chunks += count
                    report.processed_files += 1
                    manifest.upsert_record(source_key, source_hash=current_hash, output_relpaths=[], sink_ref=source_key)
                    self._state_store.save(manifest)
                except Exception as exc:
                    reason = f"{type(exc).__name__}: {exc}"
                    logger.error("indexing | failed: %s | reason: %s", source_key, reason)
                    report.failures.append(f"{source_key}: {reason}")
                    report.failed_files += 1

        report.elapsed_ms = (time.perf_counter() - started) * 1000
        return report

    def _compute_hash(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
