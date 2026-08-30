from datetime import datetime, timezone

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel
from pgvector.sqlalchemy import Vector
from app.core.config import settings

# 文档分块表，记录文档的分块内容和元数据，以及关联关系
class Chunk(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id", nullable=False, index=True)
    chunk_index: int = Field(nullable=False)  # 在文档内的顺序，0-based
    content: str = Field(nullable=False)
    char_count: int = Field(nullable=False)  # 后续排查向量检索问题时有用
    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(settings.embedding_dimensions), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )