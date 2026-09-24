from datetime import datetime

from sqlmodel import SQLModel

from app.models.document_file import ExtractionStatus


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
    processing_status: ExtractionStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
