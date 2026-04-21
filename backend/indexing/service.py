from __future__ import annotations

import re
from pathlib import Path
from backend.indexing.engine import Qwen3EmbeddingEngine
from backend.indexing.qdrant_store import QdrantStore
from backend.indexing.splitter import MarkdownHeadingSplitter
from backend.indexing.models import StandardChunk, SearchQuery, SearchResult, StandardMetadata


class IndexingService:
    def __init__(self, engine: Qwen3EmbeddingEngine | None = None) -> None:
        self._engine = engine # 延迟加载或外部注入
        self._store = QdrantStore()
        self._splitter = MarkdownHeadingSplitter()

    def index_file(self, content: str, file_name: str, standard_id: str, source_key: str) -> int:
        """切片、向量化并入库"""
        import gc
        import torch

        self._store.ensure_collection()

        # 1. 切片 (内部会处理 standard_id 规范化)
        chunks = self._splitter.split(content, file_name, standard_id)
        if not chunks:
            return 0

        # 2. 分批向量化 (防止显存溢出)
        batch_size = 32  # 从96降低到32，更激进的显存管理
        for batch_start in range(0, len(chunks), batch_size):
            batch_end = min(batch_start + batch_size, len(chunks))
            batch_chunks = chunks[batch_start:batch_end]
            texts_to_embed = [c.full_context_text for c in batch_chunks]
            vectors = self._engine.embed_texts(texts_to_embed)

            for i, chunk in enumerate(batch_chunks):
                chunk.vector = vectors[i]

            # 批后清理
            del vectors, texts_to_embed, batch_chunks
            gc.collect()
            torch.cuda.empty_cache()

        # 3. 分批入库 (防止payload超过Qdrant限制，自适应降级)
        import logging
        logger = logging.getLogger(__name__)

        self._store.delete_by_source_key(source_key)
        batch_sizes = [256, 64, 32, 16, 8]

        for batch_size in batch_sizes:
            try:
                for batch_start in range(0, len(chunks), batch_size):
                    batch_end = min(batch_start + batch_size, len(chunks))
                    self._store.upsert_chunks(chunks[batch_start:batch_end], source_key=source_key)
                if batch_size < 256:
                    logger.info("Successfully indexed with batch_size=%d: %s", batch_size, file_name)
                break  # 成功，退出重试循环
            except Exception as e:
                # 如果是payload太大的错误且还有更小的batch_size可用，继续尝试
                if ("Payload error" in str(e) or "payload" in str(e).lower()) and batch_size > batch_sizes[-1]:
                    logger.warning("Payload too large with batch_size=%d, retrying with smaller batch: %s", batch_size, file_name)
                    self._store.delete_by_source_key(source_key)
                    continue
                else:
                    raise

        return len(chunks)

    def search(self, query: SearchQuery) -> list[SearchResult]:
        """执行混合检索：规范化过滤 + 向量召回 + Reranker 精排"""
        
        # 1. 过滤器规范化
        processed_filters = {}
        if query.filters:
            for k, v in query.filters.items():
                if k == "standard_id" and v:
                    processed_filters[k] = re.sub(r'[^a-z0-9]', '', str(v).lower())
                else:
                    processed_filters[k] = v

        # 2. 向量化 Query
        instructed_query = f"Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:{query.query}"
        query_vector = self._engine.embed_texts([instructed_query])[0]
        
        # 3. 粗排召回 (召回更多数量以便精排)
        top_n = max(20, query.top_k * 3)
        points = self._store.search(
            vector=query_vector,
            filters=processed_filters,
            top_k=top_n
        )
        
        if not points:
            return []

        # 4. 精排阶段 (Rerank)
        doc_texts = [p.payload.get("full_context_text", p.payload.get("text", "")) for p in points]
        rerank_scores = self._engine.rerank(query.query, doc_texts)
        
        # 5. 组合结果并重新排序
        results = []
        for i, p in enumerate(points):
            metadata = StandardMetadata(
                standard_id=p.payload.get("standard_id"),
                file_name=p.payload.get("file_name"),
                heading_path=p.payload.get("heading_path", []),
                page_num=p.payload.get("page_num")
            )
            results.append(SearchResult(
                text=p.payload.get("text"),
                score=rerank_scores[i] if i < len(rerank_scores) else p.score,
                metadata=metadata
            ))
            
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:query.top_k]

    def reset_all(self) -> None:
        self._store.delete_collection()
        self._store.ensure_collection()
