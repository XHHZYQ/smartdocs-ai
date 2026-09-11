from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.db import get_session
from app.core.deps import get_current_user
from app.core.response import EnvelopeRoute
from app.core.security import create_access_token
from app.models.tenant import Tenant, TenantMembership, TenantRole
from app.models.user import User
from app.schemas.tenant import MembershipRead, SelectTenantRequest, TenantCreate, TenantRead
from app.schemas.user import AccessTokenResponse

router = APIRouter(prefix="/tenants", tags=["tenants"], route_class=EnvelopeRoute)


# 创建租户:当前用户自动成为 owner
# 用 get_current_user(只校验身份)而非租户上下文——
# 因为"创建租户"本来就是还没有租户时要做的事
@router.post("/create", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Tenant:
    existing = await session.exec(select(Tenant).where(Tenant.slug == payload.slug))
    if existing.first() is not None:
        raise HTTPException(status_code=400, detail="Slug already taken")

    tenant = Tenant(name=payload.name, slug=payload.slug)
    session.add(tenant)
    await session.flush()
    await session.refresh(tenant)

    session.add(
        TenantMembership(user_id=current_user.id, tenant_id=tenant.id, role=TenantRole.OWNER)
    )
    await session.commit()
    await session.refresh(tenant)
    return tenant


# 列出当前用户所属的全部租户 + 各自角色,给前端"切换工作区"下拉框用
@router.get("/mine", response_model=list[MembershipRead])
async def list_my_tenants(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[MembershipRead]:
    result = await session.exec(
        select(TenantMembership, Tenant.name, Tenant.slug)
        .join(Tenant, TenantMembership.tenant_id == Tenant.id)
        .where(TenantMembership.user_id == current_user.id)
    )
    return [
        MembershipRead(tenant_id=m.tenant_id, tenant_name=name, tenant_slug=slug, role=m.role)
        for m, name, slug in result.all()
    ]


# 选定租户作为当前工作区,换发带 tid + role claim 的新 access token
@router.post("/select", response_model=AccessTokenResponse)
async def select_tenant(
    payload: SelectTenantRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> AccessTokenResponse:
    result = await session.exec(
        select(TenantMembership).where(
            TenantMembership.user_id == current_user.id,
            TenantMembership.tenant_id == payload.tenant_id,
        )
    )
    membership = result.first()
    if membership is None:
        raise HTTPException(status_code=403, detail="Not a member of this tenant")

    return AccessTokenResponse(
        access_token=create_access_token(
            current_user.id, tenant_id=membership.tenant_id, role=membership.role.value
        )
    )