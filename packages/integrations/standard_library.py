from __future__ import annotations

import re
from pathlib import Path

from packages.core.models import SourceRef, StandardDocumentRecord

from .settings import get_settings
from .standard_store import StandardIndexStore


ALNUM_RE = re.compile(r"[A-Za-z0-9]+")


def normalize_standard_key(value: str | Path) -> str:
    text = str(value or "")
    return "".join(part.lower() for part in ALNUM_RE.findall(text))


class StandardLibrary:
    def __init__(self, standards_dir: Path | None = None) -> None:
        settings = get_settings()
        self.standards_dir = standards_dir or settings.standards_dir
        self.index_enable = settings.standard_index_enable
        self.index_store = StandardIndexStore(settings.standard_index_dir, debug=settings.standard_index_debug)

    def find_by_codes(self, codes: list[str]) -> list[SourceRef]:
        if not self.standards_dir.exists():
            return []

        indexed_docs_by_key = {self._record_key(record): record for record in self.list_indexed_docs() if self._record_key(record)}
        refs: list[SourceRef] = []
        for code in codes:
            standard_key = normalize_standard_key(code)
            if not standard_key:
                continue
            record = indexed_docs_by_key.get(standard_key)
            if record is not None:
                refs.append(SourceRef(kind="standard_file", path=str(record.path), label=code))
                continue
            for path in sorted(self.standards_dir.rglob("*")):
                if not path.is_file():
                    continue
                if normalize_standard_key(path.stem) != standard_key:
                    continue
                refs.append(SourceRef(kind="standard_file", path=str(path), label=code))
                break
        return refs

    def list_indexed_docs(self) -> list[StandardDocumentRecord]:
        if not self.index_enable:
            return []
        return self.index_store.load_manifest().documents

    def has_index_for_path(self, path: str | Path) -> bool:
        target = str(path)
        return any(record.path == target for record in self.list_indexed_docs())

    def find_docs_by_codes(self, codes: list[str]) -> list[StandardDocumentRecord]:
        standard_keys = [normalize_standard_key(code) for code in codes if normalize_standard_key(code)]
        if not standard_keys:
            return []

        matched: list[StandardDocumentRecord] = []
        seen_doc_ids: set[str] = set()
        for record in self.list_indexed_docs():
            if record.doc_id in seen_doc_ids:
                continue
            if self._record_key(record) not in standard_keys:
                continue
            seen_doc_ids.add(record.doc_id)
            matched.append(record)
        return matched

    def _record_key(self, record: StandardDocumentRecord) -> str:
        return (
            normalize_standard_key(record.standard_key)
            or normalize_standard_key(record.standard_code)
            or normalize_standard_key(record.doc_id)
            or normalize_standard_key(Path(record.path).stem)
        )
