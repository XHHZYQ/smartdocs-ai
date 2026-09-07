from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.db import get_session
from app.core.deps import get_current_user
from app.core.response import EnvelopeRoute
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.user import User
from app.schemas.search import SearchRequest, SearchResult
from app.services.retrieval import retrieve_chunks

router = APIRouter(prefix="/search", tags=["search"], route_class=EnvelopeRoute)

# 通过chunk搜索文档
# 前端关键字转换为向量，再与数据库中的向量进行相似度计算，返回相似度最高的文档
@router.post("/chunk", response_model=list[SearchResult])
async def search_chunks(
    payload: SearchRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[SearchResult]:
    all_columns = await retrieve_chunks(
        session, current_user.id, payload.query, payload.top_k
    )

    return [
        SearchResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_title=title,
            content=chunk.content,
            distance=dist,
        )
        for chunk, title, dist in all_columns
    ]