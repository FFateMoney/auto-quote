from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from packages.core.models import FormRow, StandardChunk, StandardEvidence, StandardResolutionResult

from .standard_retriever import RetrievedChunkCandidate, StandardRetriever


MAX_PARENT_EXPANSIONS = 2
MIN_CHUNK_TEXT_LENGTH = 80


def _section_depth(section_id: str) -> int:
    if "." in section_id:
        return section_id.count(".") + 1
    if "-" in section_id:
        return section_id.count("-") + 1
    return 1


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
        candidates = self.retriever.retrieve_seed_candidates_for_row(row)
        if not candidates:
            return self._missing(row, "未命中任何标准候选片段，按本地无标准处理")

        usable_candidates = [candidate for candidate in candidates if self._is_seed_candidate(candidate.chunk)]
        if not usable_candidates:
            return self._missing(row, "未命中三级标题片段，按本地无标准处理")
        best_candidate = usable_candidates[0]
        return self._resolve_candidate(
            row,
            best_candidate,
            target_fields=target_fields or [],
            run_dir=run_dir,
        )

    def _resolve_candidate(
        self,
        row: FormRow,
        candidate: RetrievedChunkCandidate,
        *,
        target_fields: list[str],
        run_dir: Path | None = None,
    ) -> StandardResolutionResult:
        notes = [f"候选三级标题 {candidate.chunk.section_id} score={candidate.score:.3f}"]
        chunks = self.retriever.load_chunks_for_doc(candidate.doc.doc_id)
        family_delimiter = self._family_delimiter(candidate.chunk.section_id)
        current_scope_id = candidate.chunk.section_id
        include_descendants = False
        expansions_used = 0
        evidences: list[StandardEvidence] = []
        seen_chunk_ids: set[str] = set()

        while True:
            scoped_chunks = self._collect_scope_chunks(
                scope_id=current_scope_id,
                chunks=chunks,
                family_delimiter=family_delimiter,
                include_descendants=include_descendants,
                exclude_chunk_ids=seen_chunk_ids,
            )
            if not scoped_chunks:
                if evidences:
                    notes.append(f"{self._scope_label(current_scope_id, include_descendants)}: 无新增章节内容，停止继续扩展")
                    return StandardResolutionResult(
                        row_id=row.row_id,
                        status="resolved",
                        evidences=evidences,
                        notes=notes,
                    )
                notes.append(f"{self._scope_label(current_scope_id, include_descendants)}: 片段内容异常，按本地无标准处理")
                return self._missing(row, *notes)

            evidence = self._build_scope_evidence(
                doc=candidate.doc,
                scope_id=current_scope_id,
                scope_chunks=scoped_chunks,
                include_descendants=include_descendants,
                score=candidate.score,
                reasons=candidate.reasons,
            )
            evidence.match_reasons = [
                *evidence.match_reasons,
                f"target_fields={','.join(target_fields) if target_fields else '-'}",
            ]
            evidences.append(evidence)
            seen_chunk_ids.update(chunk.chunk_id for chunk in scoped_chunks)
            notes.append(f"纳入章节范围 {evidence.section_id or evidence.chunk_id} | 新增块数={len(scoped_chunks)}")

            if expansions_used >= MAX_PARENT_EXPANSIONS:
                return StandardResolutionResult(
                    row_id=row.row_id,
                    status="resolved",
                    evidences=evidences,
                    notes=notes,
                )

            parent_scope_id = self._parent_scope_id(current_scope_id)
            if not parent_scope_id:
                if evidences:
                    return StandardResolutionResult(
                        row_id=row.row_id,
                        status="resolved",
                        evidences=evidences,
                        notes=notes,
                    )
                notes.append(f"{evidence.section_id or evidence.chunk_id}: 找不到上一级章节范围，按本地无标准处理")
                return self._missing(row, *notes)

            expansions_used += 1
            current_scope_id = parent_scope_id
            include_descendants = True
            notes.append(f"可继续扩展到章节范围 {self._scope_label(current_scope_id, include_descendants)}")

    def _is_seed_candidate(self, chunk: StandardChunk) -> bool:
        return _section_depth(chunk.section_id) == 3 and self._is_usable_chunk(chunk)

    def _is_usable_chunk(self, chunk: StandardChunk) -> bool:
        text = str(chunk.text or "").strip()
        if len(text) < MIN_CHUNK_TEXT_LENGTH:
            return False
        if "....." in text or "·····" in text:
            return False
        if chunk.chunk_type == "page_fallback":
            return False
        return True

    def _family_delimiter(self, section_id: str) -> str:
        if "." in section_id:
            return "."
        if "-" in section_id:
            return "-"
        return ""

    def _parent_scope_id(self, section_id: str) -> str:
        if "." in section_id:
            return section_id.rsplit(".", 1)[0]
        if "-" in section_id:
            return section_id.rsplit("-", 1)[0]
        return ""

    def _scope_label(self, scope_id: str, include_descendants: bool) -> str:
        return f"{scope_id}.*" if include_descendants else scope_id

    def _collect_scope_chunks(
        self,
        *,
        scope_id: str,
        chunks: list[StandardChunk],
        family_delimiter: str,
        include_descendants: bool,
        exclude_chunk_ids: set[str] | None = None,
    ) -> list[StandardChunk]:
        scope_chunks: list[StandardChunk] = []
        exclude_chunk_ids = exclude_chunk_ids or set()
        prefix = f"{scope_id}{family_delimiter}" if include_descendants and family_delimiter else ""
        for chunk in chunks:
            section_id = str(chunk.section_id or "").strip()
            if not section_id:
                continue
            if chunk.chunk_id in exclude_chunk_ids:
                continue
            if section_id == scope_id or (prefix and section_id.startswith(prefix)):
                if self._is_usable_chunk(chunk):
                    scope_chunks.append(chunk)
        return scope_chunks

    def _build_scope_evidence(
        self,
        *,
        doc,
        scope_id: str,
        scope_chunks: list[StandardChunk],
        include_descendants: bool,
        score: float,
        reasons: list[str],
    ) -> StandardEvidence:
        exact_chunk = next((chunk for chunk in scope_chunks if chunk.section_id == scope_id), None)
        label = self._scope_label(scope_id, include_descendants)
        title = exact_chunk.section_title if exact_chunk is not None else f"章节范围 {label}"
        page_start = min(chunk.page_start for chunk in scope_chunks)
        page_end = max(chunk.page_end for chunk in scope_chunks)
        text_parts: list[str] = []
        for chunk in scope_chunks:
            text_parts.append(f"## {chunk.section_id} {chunk.section_title}".strip())
            text_parts.append(chunk.text.strip())
        return StandardEvidence(
            chunk_id=f"{doc.doc_id}::{label}",
            standard_code=doc.standard_code,
            doc_title=doc.title,
            path=doc.path,
            page_start=page_start,
            page_end=page_end,
            section_id=label,
            section_title=title,
            score=score,
            match_reasons=[*reasons, f"scope={label}", f"scope_chunks={len(scope_chunks)}"],
            text="\n\n".join(part for part in text_parts if part).strip(),
        )

    def _missing(self, row: FormRow, *notes: str) -> StandardResolutionResult:
        return StandardResolutionResult(
            row_id=row.row_id,
            status="missing",
            evidences=[],
            notes=[note for note in notes if note],
        )
