from datetime import datetime

from sqlmodel import SQLModel


class DocumentCreate(SQLModel):
    title: str
    content: str


class DocumentUpdate(SQLModel):
    title: str | None = None
    content: str | None = None


class DocumentRead(SQLModel):
    id: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime
