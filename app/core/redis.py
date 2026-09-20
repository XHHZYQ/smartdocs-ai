from collections.abc import AsyncGenerator

import redis.asyncio as redis
from loguru import logger

from app.core.config import settings

# 全局单例，lifespan 里初始化 / 关闭
redis_client: redis.Redis | None = None


async def init_redis() -> None:
    """应用启动时调用，建立连接池。"""
    global redis_client
    redis_client = redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,  # 直接拿 str，省去手动 decode
    )
    # 探活，启动时就能发现 Redis 连不上
    await redis_client.ping()
    logger.info("Redis connected: {}", settings.redis_url)


async def close_redis() -> None:
    """应用关闭时调用，优雅断开。"""
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None
        logger.info("Redis connection closed")


async def get_redis() -> redis.Redis:
    """FastAPI Depends 用的获取方式。"""
    if redis_client is None:
        raise RuntimeError("Redis is not initialized. Check lifespan.")
    return redis_client