from __future__ import annotations

import logging
import requests
from dataclasses import dataclass
from backend.common.models import StandardDocumentRecord
from backend.quote.models import FormRow, StandardEvidence
from backend.quote.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievedChunkCandidate:
    # 为了兼容旧版 Resolver 逻辑，保留这个结构
    doc: StandardDocumentRecord
    chunk: object # 对应返回的 Payload
    score: float
    reasons: list[str]


class StandardRetriever:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.indexing_service_base_url
        self.top_k = max(1, self.settings.standard_retrieval_top_k)

    def retrieve_for_rows(self, rows: list[FormRow]) -> dict[str, list[StandardEvidence]]:
        return {row.row_id: self.retrieve_for_row(row) for row in rows}

    def retrieve_for_row(self, row: FormRow) -> list[StandardEvidence]:
        candidates = self.retrieve_seed_candidates_for_row(row)
        if not candidates:
            return []
            
        evidences = []
        for c in candidates:
            # 将 indexing 返回的 payload 映射为 StandardEvidence
            payload = c.chunk
            evidences.append(StandardEvidence(
                chunk_id=f"qdrant_{row.row_id}",
                standard_code=payload.get("standard_id", ""),
                doc_title=payload.get("file_name", ""),
                path=payload.get("file_name", ""),
                page_start=payload.get("page_num") or 0,
                page_end=payload.get("page_num") or 0,
                section_id=" > ".join(payload.get("heading_path", [])),
                section_title=payload.get("heading_path", [])[-1] if payload.get("heading_path") else "",
                score=c.score,
                match_reasons=c.reasons,
                text=payload.get("text", "")
            ))
        return evidences[:self.top_k]

    def retrieve_seed_candidates_for_row(self, row: FormRow) -> list[RetrievedChunkCandidate]:
        """
        请求本地 indexing 服务进行混合检索。
        具备强容错能力：如果服务报错，则返回空结果，不中断主流程。
        """
        if not row.standard_codes:
            # 如果没有标准号，尝试做纯语义检索，或者按需返回空
            return self._call_indexing_service(row.source_text, None)

        all_candidates = []
        for code in row.standard_codes:
            candidates = self._call_indexing_service(
                query=f"{row.canonical_test_type} {row.conditions_text}",
                standard_id=code
            )
            all_candidates.extend(candidates)
        
        all_candidates.sort(key=lambda x: x.score, reverse=True)
        return all_candidates

    def _call_indexing_service(self, query: str, standard_id: str | None) -> list[RetrievedChunkCandidate]:
        url = f"{self.base_url}/search"
        payload = {
            "query": query,
            "top_k": self.top_k,
            "filters": {"standard_id": standard_id} if standard_id else None
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                logger.warning("indexing_service_error: status=%s body=%s", response.status_code, response.text)
                return []
            
            data = response.json()
            candidates = []
            for item in data:
                # item 结构由 indexing 服务的 SearchResult 定义
                meta = item.get("metadata", {})
                doc_record = StandardDocumentRecord(
                    doc_id=meta.get("standard_id", "unknown"),
                    standard_code=meta.get("standard_id", ""),
                    title=meta.get("file_name", ""),
                    path=meta.get("file_name", "")
                )
                
                candidates.append(RetrievedChunkCandidate(
                    doc=doc_record,
                    chunk=meta | {"text": item.get("text")}, # 合并 payload
                    score=item.get("score", 0.0),
                    reasons=[f"v_score={item.get('score', 0.0):.3f}"]
                ))
            return candidates

        except Exception as e:
            logger.error("failed_to_connect_indexing_service: %s", e)
            # 容错返回：服务挂了也不影响大流程，只是没有证据支持
            return []

    def load_chunks_for_doc(self, doc_id: str) -> list:
        # 为了兼容旧版 Resolver 的接口，但 Qdrant 模式下通常不需要全量加载
        return []
