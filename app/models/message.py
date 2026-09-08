from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


# 消息表，一条 user 提问或一条 assistant 回答对应一条记录
class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", nullable=False, index=True)
    role: MessageRole = Field(nullable=False)
    content: str = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )