from datetime import datetime, timezone

from sqlmodel import Field, SQLModel
from sqlalchemy import Column, DateTime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", nullable=False, index=True)
    title: str = Field(max_length=255, nullable=False, index=True)
    content: str  # 先只存原始文本，不做切片/向量化
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

