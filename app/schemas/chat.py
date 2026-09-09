from sqlmodel import SQLModel


class ChatRequest(SQLModel):
    conversation_id: int | None = None
    query: str
    top_k: int = 5