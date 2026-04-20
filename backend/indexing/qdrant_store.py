from __future__ import annotations

import uuid
from qdrant_client import QdrantClient, models
from backend.indexing.models import StandardChunk, StandardMetadata
from backend.indexing.settings import IndexingSettings, get_settings


class QdrantStore:
    def __init__(self, settings: IndexingSettings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = QdrantClient(url=self._settings.qdrant_url, api_key=self._settings.qdrant_api_key)
        self._collection_name = self._settings.collection_name

    def ensure_collection(self) -> None:
        """确保 Collection 存在且配置正确"""
        collections = self._client.get_collections().collections
        exists = any(c.name == self._collection_name for c in collections)
        
        if not exists:
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=self._settings.vector_size,
                    distance=models.Distance.COSINE
                )
            )
            # 为 standard_id 创建 Payload 索引
            self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name="standard_id",
                field_schema=models.PayloadSchemaType.KEYWORD
            )

    def upsert_chunks(self, chunks: list[StandardChunk]) -> None:
        points = []
        for chunk in chunks:
            points.append(
                models.PointStruct(
                    id=chunk.id,
                    vector=chunk.vector,
                    payload={
                        "text": chunk.text,
                        "full_context_text": chunk.full_context_text,
                        "standard_id": chunk.metadata.standard_id,
                        "file_name": chunk.metadata.file_name,
                        "heading_path": chunk.metadata.heading_path,
                        "page_num": chunk.metadata.page_num
                    }
                )
            )
        self._client.upsert(
            collection_name=self._collection_name,
            points=points
        )

    def delete_by_file(self, file_name: str) -> None:
        """根据文件名删除索引，用于更新前的清理"""
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="file_name",
                            match=models.MatchValue(value=file_name)
                        )
                    ]
                )
            )
        )

    def search(self, vector: list[float], filters: dict | None = None, top_k: int = 5) -> list[models.ScoredPoint]:
        q_filter = None
        if filters:
            must_conditions = []
            for key, val in filters.items():
                if val:
                    must_conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=val)
                        )
                    )
            if must_conditions:
                q_filter = models.Filter(must=must_conditions)
        
        return self._client.search(
            collection_name=self._collection_name,
            query_vector=vector,
            query_filter=q_filter,
            limit=top_k,
            with_payload=True
        )

    def delete_collection(self) -> None:
        self._client.delete_collection(self._collection_name)
