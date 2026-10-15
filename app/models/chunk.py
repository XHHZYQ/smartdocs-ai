from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer
from sqlmodel import Field, SQLModel

from app.core.config import settings


# 文档分块表，记录文档的分块内容和元数据，以及关联关系
class Chunk(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    document_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("document.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    chunk_index: int = Field(nullable=False)  # 在文档内的顺序，0-based
    content: str = Field(nullable=False)
    char_count: int = Field(nullable=False)  # 后续排查向量检索问题时有用
    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(settings.embedding_dimensions), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # 向量检索 ORDER BY embedding <=> ?（cosine 距离）的 ANN 索引。
    # postgresql_ops 必须与查询算子匹配（cosine <=> → vector_cosine_ops），
    # 否则优化器不会使用这个索引。HNSW 相比 IVFFlat 无需训练、召回率更高，
    # 适合数据量持续增长的多租户场景。
    __table_args__ = (
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
