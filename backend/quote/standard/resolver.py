from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.quote.models import FormRow, StandardEvidence, StandardResolutionResult
from backend.quote.standard.retriever import RetrievedChunkCandidate, StandardRetriever


MIN_CHUNK_TEXT_LENGTH = 80


@dataclass(slots=True)
class StandardResolver:
    retriever: StandardRetriever = field(default_factory=StandardRetriever)

    def resolve_for_rows(
        self,
        rows: list[FormRow],
        *,
        target_fields_by_row: dict[str, list[str]] | None = None,
        run_dir: Path | None = None,
    ) -> dict[str, StandardResolutionResult]:
        target_fields_by_row = target_fields_by_row or {}
        return {
            row.row_id: self.resolve_for_row(
                row,
                target_fields=target_fields_by_row.get(row.row_id) or [],
                run_dir=run_dir,
            )
            for row in rows
        }

    def resolve_for_row(
        self,
        row: FormRow,
        *,
        target_fields: list[str] | None = None,
        run_dir: Path | None = None,
    ) -> StandardResolutionResult:
        del run_dir
        candidates = self.retriever.retrieve_seed_candidates_for_row(row)
        if not candidates:
            return self._missing(row, "未命中任何标准候选片段，按本地无标准处理")

        usable_candidates = [candidate for candidate in candidates if self._is_usable_candidate(candidate)]
        if not usable_candidates:
            return self._missing(row, "命中了候选片段，但正文过短或缺少章节信息")

        evidences = [
            self._candidate_to_evidence(candidate, target_fields=target_fields or [])
            for candidate in usable_candidates
        ]
        notes = [
            f"候选标准片段 {evidence.section_id or evidence.chunk_id} score={evidence.score:.3f}"
            for evidence in evidences
        ]
        return StandardResolutionResult(row_id=row.row_id, status="resolved", evidences=evidences, notes=notes)

    def _is_usable_candidate(self, candidate: RetrievedChunkCandidate) -> bool:
        text = self._chunk_text(candidate).strip()
        if len(text) < MIN_CHUNK_TEXT_LENGTH:
            return False
        return bool(self._chunk_heading_path(candidate))

    def _candidate_to_evidence(
        self,
        candidate: RetrievedChunkCandidate,
        *,
        target_fields: list[str],
    ) -> StandardEvidence:
        heading_path = self._chunk_heading_path(candidate)
        section_id = " > ".join(heading_path)
        page_num = self._chunk_page_num(candidate)
        standard_code = self._chunk_standard_id(candidate)
        file_name = self._chunk_file_name(candidate)
        text = self._chunk_text(candidate).strip()
        reasons = list(candidate.reasons)
        reasons.append(f"target_fields={','.join(target_fields) if target_fields else '-'}")
        return StandardEvidence(
            chunk_id=self._chunk_id(candidate),
            standard_code=standard_code,
            doc_title=file_name,
            path=file_name,
            page_start=page_num,
            page_end=page_num,
            section_id=section_id,
            section_title=heading_path[-1] if heading_path else "",
            score=candidate.score,
            match_reasons=reasons,
            text=text,
        )

    def _chunk_id(self, candidate: RetrievedChunkCandidate) -> str:
        section_id = " > ".join(self._chunk_heading_path(candidate)) or "unknown-section"
        page_num = self._chunk_page_num(candidate)
        return f"{self._chunk_standard_id(candidate)}::{section_id}::p{page_num}"

    def _chunk_standard_id(self, candidate: RetrievedChunkCandidate) -> str:
        return str(self._chunk_get(candidate, "standard_id") or candidate.doc.standard_code or "").strip()

    def _chunk_file_name(self, candidate: RetrievedChunkCandidate) -> str:
        return str(self._chunk_get(candidate, "file_name") or candidate.doc.title or candidate.doc.path or "").strip()

    def _chunk_page_num(self, candidate: RetrievedChunkCandidate) -> int:
        value = self._chunk_get(candidate, "page_num")
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _chunk_heading_path(self, candidate: RetrievedChunkCandidate) -> list[str]:
        value = self._chunk_get(candidate, "heading_path")
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _chunk_text(self, candidate: RetrievedChunkCandidate) -> str:
        return str(self._chunk_get(candidate, "text") or "").strip()

    def _chunk_get(self, candidate: RetrievedChunkCandidate, key: str):
        chunk = candidate.chunk
        if isinstance(chunk, dict):
            return chunk.get(key)
        return getattr(chunk, key, None)

    def _missing(self, row: FormRow, *notes: str) -> StandardResolutionResult:
        return StandardResolutionResult(
            row_id=row.row_id,
            status="missing",
            evidences=[],
            notes=[note for note in notes if note],
        )
