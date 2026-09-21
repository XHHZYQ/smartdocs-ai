import json
from typing import Any

import redis.asyncio as redis
from loguru import logger

from app.core.redis import get_redis

# 默认 TTL（秒），列表类接口用短一点
DEFAULT_TTL = 60


def build_cache_key(prefix: str, **parts: Any) -> str:
    """把参数拼成稳定、可读的 Redis key。
    例: docs:list:tenant=12:page=1:size=10
    """
    segments = [prefix]
    for k, v in sorted(parts.items()):  # sorted 保证顺序稳定
        if v is not None:
            segments.append(f"{k}={v}")
    return ":".join(segments)


async def cache_get(key: str) -> Any | None:
    r = await get_redis()
    raw = await r.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("cache key {} has invalid JSON, treat as miss", key)
        return None


async def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    r = await get_redis()
    await r.set(key, json.dumps(value, default=str), ex=ttl)


async def cache_delete(*keys: str) -> None:
    """主动失效。传多个 key 时一次性删。"""
    if not keys:
        return
    r = await get_redis()
    await r.delete(*keys)


async def cache_delete_pattern(pattern: str) -> None:
    """按前缀批量删，生产环境不要用 r.keys()，r.scan_iter() 更安全。
    例: docs:list:tenant=12:*
    """
    r = await get_redis()
    async for key in r.scan_iter(match=pattern, count=100):
        await r.delete(key)
