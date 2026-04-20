from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from pathlib import Path
from backend.cleaning.models import BatchReport
from backend.cleaning.service import CleaningService
from backend.cleaning.settings import CleaningSettings, get_settings

logger = logging.getLogger(__name__)


class CleaningLibrary:
    """批量清洗管理器：扫描 OCR 产出目录，执行清洗并输出。"""

    _CACHE_SUBDIR = ".cache"
    _HASHES_FILE = "cleaning_hashes.json"

    def __init__(self, settings: CleaningSettings | None = None) -> None:
        self._settings = settings or get_settings()
        self._service = CleaningService(self._settings)
        self._input_dir = self._settings.input_dir
        self._output_dir = self._settings.output_dir
        self._cache_dir = self._output_dir / self._CACHE_SUBDIR

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
            # 保留 .cache 目录，仅删除清洗后的文件
            for item in self._output_dir.iterdir():
                if item.name == self._CACHE_SUBDIR:
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        prev_hashes = {} if rebuild else self._read_cache()
        
        # 扫描所有 .md 文件
        input_files = sorted(self._input_dir.rglob("*.md"))
        report = BatchReport(mode=mode, total_found=len(input_files))

        next_hashes = {}
        
        for path in input_files:
            rel_path = path.relative_to(self._input_dir)
            path_key = str(rel_path)
            current_hash = self._compute_hash(path)
            next_hashes[path_key] = current_hash

            out_path = self._output_dir / rel_path

            # 增量判断：哈希未变且输出文件已存在，则跳过
            if not rebuild and prev_hashes.get(path_key) == current_hash and out_path.exists():
                report.skipped += 1
                continue

            try:
                logger.info("cleaning | processing: %s", rel_path)
                result = self._service.clean_file(path)
                
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(result.cleaned_content, encoding="utf-8")
                report.processed += 1
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                logger.error("cleaning | failed: %s | reason: %s", rel_path, reason)
                report.failures.append(f"{rel_path}: {reason}")
                report.failed += 1
                # 失败时不记录哈希，下次重试
                next_hashes.pop(path_key, None)

        self._write_cache(next_hashes)
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
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_cache(self, hashes: dict[str, str]) -> None:
        cache_file = self._cache_dir / self._HASHES_FILE
        cache_file.write_text(json.dumps(hashes, indent=2, ensure_ascii=False), encoding="utf-8")
