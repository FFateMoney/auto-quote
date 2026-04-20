from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from backend.indexing.models import IndexingReport
from backend.indexing.service import IndexingService
from backend.indexing.engine import Qwen3EmbeddingEngine
from backend.indexing.settings import IndexingSettings, get_settings

logger = logging.getLogger(__name__)


class IndexingLibrary:
    """批量索引管理器：扫描清洗后的 MD 目录，构建向量索引。"""

    _CACHE_SUBDIR = ".cache"
    _HASHES_FILE = "indexing_hashes.json"

    def __init__(self, settings: IndexingSettings | None = None) -> None:
        self._settings = settings or get_settings()
        self._input_dir = self._settings.input_dir
        self._cache_dir = self._input_dir / self._CACHE_SUBDIR
        self._service = None # 延迟加载，因为需要 Engine

    def sync(self) -> IndexingReport:
        return self._run(rebuild=False)

    def rebuild(self) -> IndexingReport:
        return self._run(rebuild=True)

    def _run(self, *, rebuild: bool) -> IndexingReport:
        mode = "rebuild" if rebuild else "sync"
        started = time.perf_counter()

        if not self._input_dir.exists():
            return IndexingReport(mode=mode)

        # 1. 只有在确定要运行且有文件时，才初始化耗时的 Embedding Engine
        input_files = sorted(self._input_dir.rglob("*.md"))
        if not input_files:
            return IndexingReport(mode=mode)

        engine = Qwen3EmbeddingEngine()
        self._service = IndexingService(engine=engine)

        if rebuild:
            self._service.reset_all()

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        prev_hashes = {} if rebuild else self._read_cache()

        # 清理已删除的文件：从Qdrant和缓存中删除
        current_file_keys = {str(p.relative_to(self._input_dir)) for p in input_files}
        deleted_keys = set(prev_hashes.keys()) - current_file_keys
        for deleted_key in deleted_keys:
            file_name = deleted_key
            logger.info("indexing | cleaning deleted file: %s", deleted_key)
            self._service._store.delete_by_file(file_name)
            prev_hashes.pop(deleted_key, None)

        report = IndexingReport(mode=mode, total_files=len(input_files))
        next_hashes = dict(prev_hashes)  # 从上次缓存开始，逐个更新

        for path in input_files:
            file_name = path.name
            path_key = str(path.relative_to(self._input_dir))
            current_hash = self._compute_hash(path)

            # 增量判断
            if not rebuild and prev_hashes.get(path_key) == current_hash:
                report.processed_files += 1
                continue

            try:
                logger.info("indexing | processing: %s", path_key)
                content = path.read_text(encoding="utf-8")

                # 提取标准号：这里假设文件名即为标准号，或者从文件名中剥离 .md
                standard_id = path.stem

                count = self._service.index_file(content, file_name, standard_id)
                report.total_chunks += count
                report.processed_files += 1

                # 成功后立即保存hash（支持断点重续）
                next_hashes[path_key] = current_hash
                self._write_cache(next_hashes)
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                logger.error("indexing | failed: %s | reason: %s", path_key, reason)
                report.failures.append(f"{path_key}: {reason}")
                report.failed_files += 1
                # 失败的文件不更新hash，下次会重试
        report.elapsed_ms = (time.perf_counter() - started) * 1000
        return report

    def _compute_hash(self, path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _read_cache(self) -> dict[str, str]:
        cache_file = self._cache_dir / self._HASHES_FILE
        if not cache_file.exists():
            return {}
        try:
            result = {}
            for line in cache_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split('\t', 1)
                if len(parts) == 2:
                    result[parts[0]] = parts[1]
            return result
        except Exception:
            return {}

    def _write_cache(self, hashes: dict[str, str]) -> None:
        cache_file = self._cache_dir / self._HASHES_FILE
        lines = [f"{k}\t{v}" for k, v in hashes.items()]
        cache_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
