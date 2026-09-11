from datetime import datetime, timezone

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


# 会话表，一次多轮对话对应一条记录
class Conversation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", nullable=False, index=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    title: str | None = Field(default=None, max_length=255)  # 先留空，后面可以用首条消息自动生成
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )