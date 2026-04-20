from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from backend.indexing.models import SearchQuery, SearchResult
from backend.indexing.service import IndexingService
from backend.indexing.engine import Qwen3EmbeddingEngine

router = APIRouter()

# 全局 Service 实例，支持预加载
_service: IndexingService | None = None

def get_service() -> IndexingService:
    global _service
    if _service is None:
        # 初始化耗时的 Embedding Engine
        engine = Qwen3EmbeddingEngine()
        _service = IndexingService(engine=engine)
    return _service


@router.post("/search", response_model=list[SearchResult])
async def search(query: SearchQuery) -> list[SearchResult]:
    """
    执行带元数据过滤的语义搜索。
    """
    try:
        service = get_service()
        return service.search(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
