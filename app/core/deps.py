from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession
from dataclasses import dataclass

from app.core.db import get_session
from app.core.security import decode_token
from app.models.tenant import Tenant
from app.models.user import User
from app.models.tenant import TenantRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

@dataclass
class TenantContext:
    tenant_id: int
    role: TenantRole


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except InvalidTokenError:
        raise unauthorized

    if payload.get("type") != "access" or payload.get("sub") is None:
        raise unauthorized

    user = await session.get(User, int(payload["sub"]))
    if user is None:
        raise unauthorized
    return user


# 租户上下文校验:要求 token 里带 tid + role claim,否则说明用户还没"选工作区"
async def get_tenant_context(
    token: str = Depends(oauth2_scheme),
) -> TenantContext:
    forbidden = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No active tenant selected. Call /tenants/select first.",
    )
    try:
        payload = decode_token(token)
    except InvalidTokenError:
        raise forbidden

    tid = payload.get("tid")
    role = payload.get("role")
    if tid is None or role is None:
        raise forbidden

    return TenantContext(tenant_id=int(tid), role=TenantRole(role))
