from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


# 消息表，记录会话中的消息，
# 每条消息对应一个用户或助手，以及一个会话
class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    conversation_id: int = Field(foreign_key="conversation.id", nullable=False, index=True)
    role: MessageRole = Field(nullable=False)
    content: str = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )