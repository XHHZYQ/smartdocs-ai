from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.db import get_session
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.user import (
    AccessTokenResponse,
    RefreshRequest,
    Token,
    UserCreate,
    UserRead,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> User:
    existing = await session.exec(select(User).where(User.email == payload.email))
    if existing.first() is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(
    # OAuth2PasswordRequestForm 字段名固定是 username/password，这里用 username 承载 email
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session),
) -> Token:
    result = await session.exec(select(User).where(User.email == form_data.username))
    user = result.first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(payload: RefreshRequest) -> AccessTokenResponse:
    try:
        token_payload = decode_token(payload.refresh_token)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if token_payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    return AccessTokenResponse(access_token=create_access_token(int(token_payload["sub"])))