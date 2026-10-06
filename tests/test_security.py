"""测试 app.core.security 模块。

纯函数测试，不依赖 DB / Redis / 外部 API。
JWT 签发/校验走真实 jwt 库（测试 .env.test 里配了固定 secret_key）。
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from jwt import InvalidTokenError

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


# ===== 密码哈希 =====


class TestPasswordHashing:
    def test_hash_and_verify_correct(self):
        plain = "MySecret123!"
        hashed = hash_password(plain)
        assert hashed != plain
        assert verify_password(plain, hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_hash_is_unique_per_call(self):
        """每次 hash 用不同 salt，结果不同"""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2
        # 但都能验证通过
        assert verify_password("same", h1)
        assert verify_password("same", h2)


# ===== Access Token =====


class TestAccessToken:
    def test_encode_and_decode(self):
        token = create_access_token(user_id=42)
        payload = decode_token(token)
        assert payload["sub"] == "42"
        assert payload["type"] == "access"
        assert "iat" in payload
        assert "exp" in payload

    def test_with_tenant_claims(self):
        token = create_access_token(user_id=1, tenant_id=10, role="owner")
        payload = decode_token(token)
        assert payload["sub"] == "1"
        assert payload["type"] == "access"
        assert payload["tid"] == 10
        assert payload["role"] == "owner"

    def test_without_tenant_has_no_claims(self):
        token = create_access_token(user_id=1)
        payload = decode_token(token)
        assert "tid" not in payload
        assert "role" not in payload

    def test_expired_token_raises(self):
        """手动构造已过期的 token"""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "1",
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        }
        expired = jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        with pytest.raises(InvalidTokenError):
            decode_token(expired)

    def test_invalid_signature_raises(self):
        """用错误的 secret 签发的 token 解码失败"""
        payload = {
            "sub": "1",
            "type": "access",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        }
        bad_token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        with pytest.raises(InvalidTokenError):
            decode_token(bad_token)


# ===== Refresh Token =====


class TestRefreshToken:
    def test_encode_and_decode(self):
        token = create_refresh_token(user_id=99)
        payload = decode_token(token)
        assert payload["sub"] == "99"
        assert payload["type"] == "refresh"

    def test_refresh_type_distinct_from_access(self):
        access = create_access_token(user_id=1)
        refresh = create_refresh_token(user_id=1)
        assert decode_token(access)["type"] == "access"
        assert decode_token(refresh)["type"] == "refresh"
