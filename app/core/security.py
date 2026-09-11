from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def _create_token(
    subject: str,
    expires_delta: timedelta,
    token_type: str,
    extra_claims: dict | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_access_token(
    user_id: int, tenant_id: int | None = None, role: str | None = None
) -> str:
    extra = {"tid": tenant_id, "role": role} if tenant_id is not None else {}
    return _create_token(
        str(user_id),
        timedelta(minutes=settings.access_token_expire_minutes),
        "access",
        extra_claims=extra,
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        str(user_id),
        timedelta(days=settings.refresh_token_expire_days),
        "refresh",
    )


def decode_token(token: str) -> dict:
    # 过期 / 签名错误都会抛 jwt.InvalidTokenError（ExpiredSignatureError 是它的子类）
    return jwt.decode(
        token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )
