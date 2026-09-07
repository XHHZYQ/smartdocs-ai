from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.chunk import Chunk
from app.models.document import Document
from app.services.embedding import get_embeddings


async def retrieve_chunks(
    session: AsyncSession, owner_id: int, query: str, top_k: int
) -> list[tuple[Chunk, str, float]]:
    """检索指定用户下、与 query 语义最相近的 Top-K chunk。
    返回 (Chunk, document_title, distance) 三元组列表，供 /search 和 /chat 共用。
    """
    query_embeddings = await get_embeddings([query])
    query_vector = query_embeddings[0]

    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")

    result = await session.exec(
        select(Chunk, Document.title, distance)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.owner_id == owner_id)
        .order_by(distance)
        .limit(top_k)
    )
    return result.all()