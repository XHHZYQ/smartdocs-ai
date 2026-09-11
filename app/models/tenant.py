from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class Tenant(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=255, nullable=False)
    slug: str = Field(max_length=100, unique=True, index=True, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class TenantRole(str, Enum):
    OWNER = "owner"    # 租户创建者,唯一能删除租户/转让所有权
    ADMIN = "admin"    # 能管理成员、改租户设置
    MEMBER = "member"  # 能读写业务资源(文档、会话)
    VIEWER = "viewer"  # 只读


class TenantMembership(SQLModel, table=True):
    """用户与租户的多对多关系表,角色挂在这张表上而不是 User 表——
    因为角色是"租户范围"的:同一个人在 A 租户是 admin,在 B 租户可能只是 viewer。
    """
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_membership_user_tenant"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", nullable=False, index=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    role: TenantRole = Field(nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )