from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class SourceType(str, Enum):
    """上传文件的来源类型"""

    PDF = "pdf"
    MARKDOWN = "markdown"


class ExtractionStatus(str, Enum):
    """文本提取处理的状态机：pending -> success / failed"""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

# 文档文件表，记录上传的文件元数据，以及关联关系
# 每个文件对应一个 DocumentFile 记录，记录文件的原始信息、内容类型、大小、来源类型等
# 解析成功后，指向生成的 Document 记录；解析失败或未开始时为 None
class DocumentFile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    original_filename: str = Field(max_length=255, nullable=False)
    content_type: str = Field(max_length=127, nullable=False)
    file_size_bytes: int = Field(nullable=False)
    source_type: SourceType = Field(nullable=False)

    extraction_status: ExtractionStatus = Field(
        default=ExtractionStatus.PENDING, nullable=False, index=True
    )
    error_message: str | None = Field(default=None, nullable=True)

    # 解析成功后指向生成的 Document；解析失败或未开始时为 None
    document_id: int | None = Field(
        default=None, foreign_key="document.id", nullable=True
    )

    # 记录上传者,用于列表接口按 owner 过滤
    owner_id: int = Field(foreign_key="user.id", nullable=True, index=True)
    uploaded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
