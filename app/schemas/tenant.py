from datetime import datetime

from sqlmodel import SQLModel

from app.models.tenant import TenantRole


class TenantCreate(SQLModel):
    name: str
    slug: str


class TenantRead(SQLModel):
    id: int
    name: str
    slug: str
    created_at: datetime


class MembershipRead(SQLModel):
    tenant_id: int
    tenant_name: str
    tenant_slug: str
    role: TenantRole


class SelectTenantRequest(SQLModel):
    tenant_id: int