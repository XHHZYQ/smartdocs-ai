from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import TenantContext, get_tenant_context
from app.core.limiter import limiter
from app.core.response import EnvelopeRoute
from app.schemas.search import SearchRequest, SearchResult
from app.services.retrieval import retrieve_chunks

router = APIRouter(prefix="/search", tags=["search"], route_class=EnvelopeRoute)


# 通过chunk搜索文档
# 前端关键字转换为向量，再与数据库中的向量进行相似度计算，返回相似度最高的文档
@router.post("/chunk", response_model=list[SearchResult])
@limiter.limit("30/minute")
async def search_chunks(
    request: Request,
    payload: SearchRequest,
    session: AsyncSession = Depends(get_session),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> list[SearchResult]:
    all_columns = await retrieve_chunks(
        session, tenant_ctx.tenant_id, payload.query, payload.top_k
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
