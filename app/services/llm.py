import json
import codecs
from collections.abc import AsyncGenerator

import httpx

from app.core.config import settings


async def stream_chat(messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
    """流式调用 Chat Completions 接口，逐段文本 yield 出去。
    调用方用 `async for text in stream_chat(...)` 消费，而不是 await 一次性拿结果。
    """
    async with httpx.AsyncClient(
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
            decoder = codecs.getincrementaldecoder("utf-8")()
            buffer = ""

            async for raw_bytes in response.aiter_bytes():
                buffer += decoder.decode(raw_bytes)
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):]
                    if payload == "[DONE]":
                        continue
                    chunk = json.loads(payload)
                    delta = chunk["choices"][0]["delta"].get("content")
                    print("原始 delta:", repr(delta))  # 临时调试，确认问题就出在这里
                    if delta:
                        yield delta