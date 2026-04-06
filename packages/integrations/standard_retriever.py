from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from packages.core.models import FormRow, StandardChunk, StandardDocumentRecord, StandardEvidence

from .embeddings import EmbeddingAdapter
from .settings import get_settings
from .standard_library import StandardLibrary
from .standard_store import StandardIndexStore


NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
TEST_TYPE_SYNONYMS: dict[str, list[str]] = {
    "高温": ["高温", "高温储存", "高温工作", "high temperature"],
    "低温": ["低温", "低温储存", "低温工作", "low temperature"],
    "湿热": ["湿热", "humidity", "humid", "climate"],
    "温度循环": ["温度循环", "温度变化", "temperature cycle", "thermal cycle"],
    "振动": ["振动", "vibration"],
    "冲击": ["冲击", "impact", "shock"],
    "盐雾": ["盐雾", "salt spray", "corrosion"],
    "防尘": ["防尘", "dust", "dust proof"],
    "防水": ["防水", "watertight", "waterproof", "water spray"],
}
PREFERRED_SECTION_TERMS = ("试验参数", "试验方法", "技术要求", "test parameters", "test method", "requirement")


@dataclass(slots=True)
class RetrievalQuery:
    query_text: str
    keyword_terms: list[str]
    numeric_terms: list[str]
    preferred_section_terms: list[str]


@dataclass(slots=True)
class RetrievedChunkCandidate:
    doc: StandardDocumentRecord
    chunk: StandardChunk
    score: float
    reasons: list[str]


class StandardRetriever:
    def __init__(
        self,
        *,
        standards: StandardLibrary | None = None,
        store: StandardIndexStore | None = None,
        embedder: EmbeddingAdapter | None = None,
    ) -> None:
        settings = get_settings()
        self.settings = settings
        self.standards = standards or StandardLibrary()
        self.store = store or StandardIndexStore(settings.standard_index_dir, debug=settings.standard_index_debug)
        self.embedder = embedder or EmbeddingAdapter()
        self.top_k = max(1, settings.standard_retrieval_top_k)
        self.expand_neighbors = settings.standard_retrieval_expand_neighbors

    def retrieve_for_rows(self, rows: list[FormRow]) -> dict[str, list[StandardEvidence]]:
        return {row.row_id: self.retrieve_for_row(row) for row in rows}

    def retrieve_for_row(self, row: FormRow) -> list[StandardEvidence]:
        candidates = self.retrieve_seed_candidates_for_row(row)
        evidences = [self.build_evidence(candidate.doc, candidate.chunk, candidate.score, candidate.reasons) for candidate in candidates]
        return self._dedupe_evidences(evidences)[: self.top_k]

    def retrieve_seed_candidates_for_row(self, row: FormRow) -> list[RetrievedChunkCandidate]:
        docs = self.standards.find_docs_by_codes(row.standard_codes)
        if not docs:
            return []

        query = self._build_query(row)
        query_vector = self.embedder.embed_query(query.query_text)
        candidates: list[RetrievedChunkCandidate] = []
        for doc in docs:
            chunks = self.store.load_chunks(doc.doc_id)
            if not chunks:
                continue
            embeddings = self.store.load_embeddings(doc.doc_id)
            candidates.extend(
                self._score_chunks(
                    doc=doc,
                    chunks=chunks,
                    embeddings=embeddings,
                    query=query,
                    query_vector=query_vector,
                )
            )

        candidates.sort(key=lambda item: item.score, reverse=True)
        return self._dedupe_candidates(candidates)

    def load_chunks_for_doc(self, doc_id: str) -> list[StandardChunk]:
        return self.store.load_chunks(doc_id)

    def build_evidence(
        self,
        doc: StandardDocumentRecord,
        chunk: StandardChunk,
        score: float,
        reasons: list[str],
    ) -> StandardEvidence:
        return StandardEvidence(
            chunk_id=chunk.chunk_id,
            standard_code=doc.standard_code,
            doc_title=doc.title,
            path=doc.path,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_id=chunk.section_id,
            section_title=chunk.section_title,
            score=score,
            match_reasons=list(reasons),
            text=chunk.text,
        )

    def _build_query(self, row: FormRow) -> RetrievalQuery:
        keyword_terms: list[str] = []
        for text in (row.canonical_test_type, row.raw_test_type, row.conditions_text, row.sample_info_text):
            keyword_terms.extend(self._extract_terms(text))

        for candidate in (row.canonical_test_type, row.raw_test_type):
            for key, synonyms in TEST_TYPE_SYNONYMS.items():
                if key and key in str(candidate or ""):
                    keyword_terms.extend(synonyms)

        numeric_terms = list(dict.fromkeys(NUMBER_RE.findall(f"{row.conditions_text} {row.sample_info_text} {row.source_text}")))
        keyword_terms = list(dict.fromkeys(term for term in keyword_terms if term))
        query_parts = keyword_terms + numeric_terms + list(PREFERRED_SECTION_TERMS)
        return RetrievalQuery(
            query_text=" ".join(query_parts).strip(),
            keyword_terms=keyword_terms,
            numeric_terms=numeric_terms,
            preferred_section_terms=list(PREFERRED_SECTION_TERMS),
        )

    def _extract_terms(self, text: str) -> list[str]:
        raw = re.split(r"[\s,，;；:/\\()（）\[\]]+", str(text or ""))
        return [token.strip() for token in raw if len(token.strip()) >= 2]

    def _score_chunks(
        self,
        *,
        doc: StandardDocumentRecord,
        chunks: list[StandardChunk],
        embeddings: np.ndarray,
        query: RetrievalQuery,
        query_vector: np.ndarray,
    ) -> list[RetrievedChunkCandidate]:
        scored: list[RetrievedChunkCandidate] = []
        for index, chunk in enumerate(chunks):
            score, reasons = self._score_chunk(
                chunk=chunk,
                query=query,
                query_vector=query_vector,
                embeddings=embeddings,
                vector_row=index,
            )
            if score <= 0:
                continue
            scored.append(
                RetrievedChunkCandidate(
                    doc=doc,
                    chunk=chunk,
                    score=score,
                    reasons=reasons,
                )
            )
        return scored

    def _score_chunk(
        self,
        *,
        chunk: StandardChunk,
        query: RetrievalQuery,
        query_vector: np.ndarray,
        embeddings: np.ndarray,
        vector_row: int,
    ) -> tuple[float, list[str]]:
        title_text = f"{chunk.section_id} {chunk.section_title}".lower()
        body_text = chunk.normalized_text.lower()
        reasons: list[str] = []
        score = 0.0

        title_hits = sum(1 for term in query.keyword_terms if term.lower() in title_text)
        if title_hits:
            score += title_hits * 4.0
            reasons.append(f"title_hits={title_hits}")

        body_hits = sum(1 for term in query.keyword_terms if term.lower() in body_text)
        if body_hits:
            score += min(body_hits, 12) * 1.2
            reasons.append(f"keyword_hits={body_hits}")

        numeric_hits = sum(1 for term in query.numeric_terms if term in chunk.text)
        if numeric_hits:
            score += numeric_hits * 1.5
            reasons.append(f"numeric_hits={numeric_hits}")

        preferred_hits = sum(1 for term in query.preferred_section_terms if term.lower() in body_text)
        if preferred_hits:
            score += preferred_hits * 0.6
            reasons.append(f"preferred_hits={preferred_hits}")

        if embeddings.ndim == 2 and 0 <= vector_row < len(embeddings):
            similarity = float(np.dot(query_vector, embeddings[vector_row]))
            if similarity > 0:
                score += similarity * 2.5
                reasons.append(f"vector={similarity:.3f}")

        if chunk.chunk_type == "section":
            score += 0.2

        return score, reasons

    def _dedupe_evidences(self, evidences: list[StandardEvidence]) -> list[StandardEvidence]:
        kept: list[StandardEvidence] = []
        seen: set[tuple[str, str]] = set()
        for item in evidences:
            key = (item.path, item.section_id or item.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            kept.append(item)
        return kept

    def _dedupe_candidates(self, candidates: list[RetrievedChunkCandidate]) -> list[RetrievedChunkCandidate]:
        kept: list[RetrievedChunkCandidate] = []
        seen: set[tuple[str, str]] = set()
        for item in candidates:
            key = (item.doc.path, item.chunk.section_id or item.chunk.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            kept.append(item)
        return kept
