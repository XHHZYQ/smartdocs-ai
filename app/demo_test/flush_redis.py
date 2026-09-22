"""Flush all Redis keys (for testing rate limit)."""
import asyncio

import redis.asyncio as r


async def main():
    c = r.from_url("redis://localhost:6379/0", decode_responses=True)
    keys = []
    async for k in c.scan_iter(match="*", count=100):
        keys.append(k)
    print("all keys before flush:", keys)
    if keys:
        await c.delete(*keys)
    await c.aclose()


asyncio.run(main())
