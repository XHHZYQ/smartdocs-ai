from datetime import datetime, timezone

from sqlmodel import Field, SQLModel
from sqlalchemy import Column, DateTime

from app.models.document_file import ExtractionStatus


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# 文档表，文档的基本信息和内容，以及关联关系
class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", nullable=False, index=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    title: str = Field(max_length=255, nullable=False, index=True)
    content: str
    # 文档处理状态机：pending -> processing -> success / failed
    # create/update 接口入队后置 processing，arq 任务完成置 success/failed
    # 默认 success 兼容历史数据（迁移时也给旧行赋 success）
    processing_status: ExtractionStatus = Field(
        default=ExtractionStatus.SUCCESS, nullable=False, index=True
    )
    error_message: str | None = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
