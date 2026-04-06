from __future__ import annotations

import argparse
import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError

from packages.core.models import StandardChunk, StandardDocumentRecord, StandardIndexManifest

from .embeddings import EmbeddingAdapter
from .settings import get_settings
from .standard_chunker import StandardChunker
from .standard_cleaner import StandardCleaner
from .standard_library import normalize_standard_key
from .standard_store import StandardIndexStore


logger = logging.getLogger(__name__)
STANDARD_CODE_RE = re.compile(
    r"(?:(?:Q[/\- ]?[A-Z]+[A-Z0-9 /\-_.]*\d{2,4})|(?:[A-Z][A-Z0-9]+(?:[/_\- ][A-Z0-9.()]+)+))",
    re.IGNORECASE,
)


@dataclass(slots=True)
class IndexBuildReport:
    processed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


class StandardIndexer:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.cleaner = StandardCleaner()
        self.chunker = StandardChunker()
        self.embedder = EmbeddingAdapter()
        self.store = StandardIndexStore(self.settings.standard_index_dir, debug=self.settings.standard_index_debug)

    def build_index(self, *, sync: bool = True, rebuild: bool = False) -> IndexBuildReport:
        if not self.settings.standard_index_enable:
            raise RuntimeError("standard_index_disabled")

        if rebuild:
            self.store.reset()

        standards_dir = self.settings.standards_dir
        manifest = self.store.load_manifest()
        hashes = {} if rebuild else self.store.load_file_hashes()
        current_paths = [
            path
            for path in sorted(standards_dir.rglob("*"))
            if path.is_file() and path.suffix.lower() == ".pdf"
        ]
        pending_paths = []
        for path in current_paths:
            path_key = str(path)
            file_hash = self._file_hash(path)
            pending_paths.append((path, path_key, file_hash))

        report = IndexBuildReport()
        next_hashes: dict[str, str] = {}
        next_records: dict[str, StandardDocumentRecord] = {record.doc_id: record for record in manifest.documents}

        existing_doc_paths = {record.path: record.doc_id for record in manifest.documents}
        live_paths = {str(path) for path in current_paths}
        for record in manifest.documents:
            if record.path in live_paths:
                continue
            self.store.delete_document(record.doc_id)
            next_records.pop(record.doc_id, None)
            report.removed.append(record.path)

        need_index_total = sum(1 for _, path_key, file_hash in pending_paths if not (sync and hashes.get(path_key) == file_hash))
        logger.info(
            "标准索引启动 | total_pdf=%s need_index=%s skipped_by_hash=%s removed=%s",
            len(current_paths),
            need_index_total,
            len(current_paths) - need_index_total,
            len(report.removed),
        )

        done_count = 0
        for path, path_key, file_hash in pending_paths:
            next_hashes[path_key] = file_hash
            if sync and hashes.get(path_key) == file_hash:
                report.skipped.append(path.name)
                self.store.clear_missing(path_key)
                continue

            done_count += 1
            logger.info("标准索引进度 | %s/%s | %s", done_count, need_index_total or 1, path.name)
            try:
                record, chunks, cleaned_pages = self._index_file(path=path, file_hash=file_hash)
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                logger.warning("标准索引跳过 | file=%s | reason=%s", path.name, reason)
                self.store.mark_missing(path_key, reason)
                report.failed.append(f"{path.name}: {reason}")
                continue

            next_records[record.doc_id] = record
            self.store.save_document_record(record)
            self.store.save_chunks(record.doc_id, chunks)
            self.store.save_embeddings(record.doc_id, self.embedder.embed_texts([chunk.normalized_text for chunk in chunks]))
            self.store.save_debug_artifacts(record.doc_id, cleaned_pages=cleaned_pages, chunks=chunks)
            self.store.clear_missing(path_key)
            existing_doc_id = existing_doc_paths.get(path_key)
            if existing_doc_id and existing_doc_id != record.doc_id:
                self.store.delete_document(existing_doc_id)
                next_records.pop(existing_doc_id, None)
            report.processed.append(path.name)

        manifest = StandardIndexManifest(documents=sorted(next_records.values(), key=lambda item: item.path))
        self.store.save_manifest(manifest)
        self.store.save_file_hashes(next_hashes)
        return report

    def _index_file(self, *, path: Path, file_hash: str) -> tuple[StandardDocumentRecord, list[StandardChunk], list[str]]:
        cleaned_pages = self._clean_pages(path)
        page_count = len(cleaned_pages)
        standard_code = self._guess_standard_code(path, cleaned_pages)
        standard_key = normalize_standard_key(standard_code) or normalize_standard_key(path.stem)
        title = self._guess_title(path, cleaned_pages)
        doc_id = self._doc_id(path, standard_key=standard_key)
        category = path.parent.name

        record = StandardDocumentRecord(
            doc_id=doc_id,
            standard_key=standard_key,
            standard_code=standard_code,
            title=title,
            path=str(path),
            category=category,
            language=self._guess_language(cleaned_pages),
            page_count=page_count,
            file_hash=file_hash,
        )
        chunks = self.chunker.chunk_document(record, cleaned_pages)
        for index, chunk in enumerate(chunks):
            chunk.vector_row = index
        record.chunk_count = len(chunks)
        return record, chunks, cleaned_pages

    def _clean_pages(self, path: Path) -> list[str]:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                decrypt_result = reader.decrypt("")
            except Exception as exc:
                raise RuntimeError("pdf_encrypted_or_protected") from exc
            if decrypt_result == 0:
                raise RuntimeError("pdf_encrypted_or_protected")
        try:
            raw_pages = [(page.extract_text() or "") for page in reader.pages]
        except FileNotDecryptedError as exc:
            raise RuntimeError("pdf_encrypted_or_protected") from exc
        except Exception as exc:
            raise RuntimeError("pdf_text_extract_failed") from exc
        return self.cleaner.clean_document_pages(raw_pages)

    def _file_hash(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _doc_id(self, path: Path, *, standard_key: str) -> str:
        if standard_key:
            return standard_key
        fallback = normalize_standard_key(path.stem)
        return fallback or hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]

    def _guess_standard_code(self, path: Path, pages: list[str]) -> str:
        sources = [path.stem]
        if pages:
            lines = [line.strip() for line in pages[0].splitlines() if line.strip()]
            sources.extend(lines[:12])
        for source in sources:
            match = STANDARD_CODE_RE.search(source)
            if match:
                return match.group(0).strip(" -_.")
        return path.stem

    def _guess_title(self, path: Path, pages: list[str]) -> str:
        if pages:
            for line in pages[0].splitlines():
                clean = line.strip()
                if not clean:
                    continue
                if len(clean) < 3:
                    continue
                return clean[:200]
        return path.stem

    def _guess_language(self, pages: list[str]) -> str:
        sample = "\n".join(pages[:3])
        has_cn = bool(re.search(r"[\u4e00-\u9fff]", sample))
        has_en = bool(re.search(r"[A-Za-z]", sample))
        if has_cn and has_en:
            return "mixed"
        if has_cn:
            return "zh"
        if has_en:
            return "en"
        return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build or sync the local standard PDF index.")
    parser.add_argument("--sync", action="store_true", help="Incrementally index added or changed PDF files.")
    parser.add_argument("--rebuild", action="store_true", help="Discard current index files and rebuild from scratch.")
    return parser


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    args = _build_parser().parse_args()
    if not args.sync and not args.rebuild:
        args.sync = True

    indexer = StandardIndexer()
    report = indexer.build_index(sync=args.sync, rebuild=args.rebuild)
    logger.info(
        "标准索引完成 | success_added=%s skipped=%s failed=%s removed=%s",
        len(report.processed),
        len(report.skipped),
        len(report.failed),
        len(report.removed),
    )
    for item in report.failed:
        logger.warning("标准索引失败项: %s", item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
