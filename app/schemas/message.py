from datetime import datetime

from sqlmodel import SQLModel

from app.models.message import MessageRole


class MessageRead(SQLModel):
    id: int
    conversation_id: int
    role: MessageRole
    content: str
    created_at: datetime