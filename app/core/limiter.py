"""slowapi 限流器封装。

类比 Fastify 的 @fastify/rate-limit,但 slowapi 的入口是装饰器 + 中间件:
- 装饰器 @limiter.limit("10/minute") 挂在路由上声明限流值
- SlowAPIMiddleware 在 main.py 注册后,会按 key_func 算出的 key 去查 Redis 计数

key_func 必须是同步函数(因为 slowapi 内部会 await 它),不能 Depends。
所以这里直接从 Authorization header 同步解析 JWT 拿 user_id,
解析失败(未登录/格式错)就回退到 IP 维度。
"""
import jwt
from fastapi import Request
from slowapi import Limiter

from app.core.config import settings


def _get_client_ip(request: Request) -> str:
    """获取真实客户端 IP。
    Nginx 反代时把真实 IP 放在 X-Forwarded-For 的第一段,优先用它;
    没有 XFF 头就直接走 request.client.host(开发场景)。
    """
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        # "1.2.3.4, 10.0.0.1" 取最左边的客户端 IP
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _decode_user_id_from_token(request: Request) -> str | None:
    """从 Authorization: Bearer <jwt> 同步解析出 sub(user_id)。
    注意:这里不做过期校验外的额外校验——deps 层会严格校验,
    key_func 只是为了拿到稳定维度,解析失败就回退到 IP。
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    try:
        # options 里不校验 exp,避免刚过期的 token 还能拿 user_id 维度计数
        # (反正这种 token 在 deps 层会被拒,只是为了让 key_func 稳定)
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
    except jwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return str(sub) if sub is not None else None


def key_func(request: Request) -> str:
    """按路由前缀选择限流维度。

    - /auth/* 用 IP(登录前没有 user_id,且要防暴破)
    - 其他接口优先用 user_id(JWT 里的 sub),拿不到就回退 IP
    """
    path = request.url.path
    if path.startswith("/auth"):
        return f"ip:{_get_client_ip(request)}"

    user_id = _decode_user_id_from_token(request)
    if user_id is not None:
        return f"user:{user_id}"
    return f"ip:{_get_client_ip(request)}"


# Limiter 实例:所有 router 都从这里 import limiter 装饰器。
# storage_uri 让 slowapi 内部用 limits 库自管 Redis 连接(与应用 redis_client 独立,
# 各管各的连接池,互不干扰)。enabled 由 main.py 控制——不注册 SlowAPIMiddleware 时,
# 装饰器记录配置但不触发拦截。
# headers_enabled 关掉:开 True 会要求每个 handler 都有 response: Response 参数,
# 侵入太大。429 响应本身已能区分限流来源,X-RateLimit-* 头非必需。
limiter = Limiter(
    key_func=key_func,
    default_limits=[settings.rate_limit_default],
    storage_uri=settings.redis_url,
)
