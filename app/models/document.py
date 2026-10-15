from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Index, desc
from sqlmodel import Field, SQLModel

from app.models.document_file import ExtractionStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


# 文档表，文档的基本信息和内容，以及关联关系
class Document(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id", nullable=False, index=True)
    # tenant_id 不加单列索引：下方 (tenant_id, created_at DESC) 复合索引的
    # 最左前缀已覆盖按 tenant_id 过滤的场景，避免重复索引浪费写入性能
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)
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
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    # 列表查询 WHERE tenant_id = ? ORDER BY created_at DESC 的复合索引：
    # 等值过滤（第一列）+ 排序（第二列）可由一次有序索引扫描完成，省掉 sort 步骤
    __table_args__ = (
        Index("ix_document_tenant_created_at", "tenant_id", desc("created_at")),
    )
