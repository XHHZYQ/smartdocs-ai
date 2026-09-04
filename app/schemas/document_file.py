from datetime import datetime

from sqlmodel import SQLModel

from app.models.document_file import ExtractionStatus, SourceType


class DocumentFileRead(SQLModel):
    id: int
    original_filename: str
    content_type: str
    file_size_bytes: int
    source_type: SourceType
    extraction_status: ExtractionStatus
    error_message: str | None
    document_id: int | None
    uploaded_at: datetime
    owner_id: int | None

class DocumentFilePage(SQLModel):
    items: list[DocumentFileRead]
    total: int