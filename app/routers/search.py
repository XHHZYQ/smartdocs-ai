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
from app.services.embedding import get_embeddings

router = APIRouter(prefix="/search", tags=["search"], route_class=EnvelopeRoute)


@router.post("", response_model=list[SearchResult])
async def search_chunks(
    payload: SearchRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[SearchResult]:
    query_embeddings = await get_embeddings([payload.query])
    query_vector = query_embeddings[0]

    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    result = await session.exec(
        select(Chunk, Document.title, distance)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.owner_id == current_user.id)
        .order_by(distance)
        .limit(payload.top_k)
    )
    allColumns = result.all()

    return [
        SearchResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_title=title,
            content=chunk.content,
            distance=dist,
        )
        for chunk, title, dist in allColumns
    ]