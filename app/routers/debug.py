from fastapi import Depends
from app.core.redis import get_redis
import redis.asyncio as redis
from fastapi import APIRouter

router = APIRouter()

@router.get("/debug/redis-ping")
async def redis_ping(r: redis.Redis = Depends(get_redis)):
    return {"pong": await r.ping()}