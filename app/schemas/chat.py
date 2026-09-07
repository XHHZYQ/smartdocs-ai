from sqlmodel import SQLModel


class ChatRequest(SQLModel):
    query: str
    top_k: int = 5