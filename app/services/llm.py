import json
import codecs
from collections.abc import AsyncGenerator

import httpx

from app.core.config import settings

class LLMServiceError(Exception):
    """LLM 服务调用失败时抛出，携带可直接展示给用户的错误信息"""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


async def stream_chat(messages: list[dict[str, str]]) -> AsyncGenerator[str, None]:
    """流式调用 Chat Completions 接口，逐段文本 yield 出去。
    调用方用 `async for text in stream_chat(...)` 消费，而不是 await 一次性拿结果。
    """
    try:
        async with httpx.AsyncClient(
            base_url=settings.embedding_base_url,
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),
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
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    if status == 401:
                        raise LLMServiceError("LLM 服务鉴权失败，请检查 API Key") from e
                    if status == 429:
                        raise LLMServiceError("请求过于频繁，请稍后再试") from e
                    raise LLMServiceError(f"LLM 服务返回错误（状态码 {status}）") from e

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
                        if delta:
                            yield delta
    except httpx.TimeoutException as e:
        raise LLMServiceError("LLM 服务响应超时，请稍后重试") from e
    except httpx.RequestError as e:
        raise LLMServiceError("无法连接 LLM 服务，请检查网络或稍后重试") from e