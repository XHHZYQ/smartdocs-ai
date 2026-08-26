from datetime import datetime, timezone

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class Chunk(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    document_id: int = Field(foreign_key="document.id", nullable=False, index=True)
    chunk_index: int = Field(nullable=False)  # 在文档内的顺序，0-based
    content: str = Field(nullable=False)
    char_count: int = Field(nullable=False)  # 后续排查向量检索问题时有用
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )