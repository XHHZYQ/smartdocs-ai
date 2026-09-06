import json
from collections.abc import AsyncGenerator

import httpx2

from app.core.config import settings


async def stream_chat(messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
    """流式调用 Chat Completions 接口，逐段文本 yield 出去。
    调用方用 `async for text in stream_chat(...)` 消费，而不是 await 一次性拿结果。
    """
    async with httpx2.AsyncClient(
        base_url=settings.embedding_base_url, timeout=60
    ) as client:
        async with client.stream(
            "POST",
            "/chat/completions",
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
            json={
                "model": settings.chat_model,
                "messages": messages,
                "stream": True,
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue  # SSE 帧之间的空行、或非 data 行，直接跳过

                payload = line[len("data: "):]
                if payload == "[DONE]":
                    # break
                    continue  # 跳过 [DONE] 行, 解决 generator didn't stop after athrow() 报错

                chunk = json.loads(payload)
                delta = chunk["choices"][0]["delta"].get("content")
                if delta:
                    yield delta