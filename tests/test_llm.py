"""测试 app.services.llm.stream_chat —— SSE 流式解析 + 错误映射。

respx 支持 content 为字节迭代器，天然模拟流式响应；
还可以把字节切成任意边界，验证增量解码器处理跨 chunk 的 JSON。
"""

import httpx
import pytest
import respx

from app.core.config import settings
from app.services.llm import LLMServiceError, stream_chat

CHAT_URL = f"{settings.embedding_base_url}/chat/completions"


def _sse(*events: str) -> bytes:
    """把若干 SSE 事件拼成字节流，事件间以空行分隔。"""
    return ("\n\n".join(events) + "\n\n").encode("utf-8")


def _aiter(*chunks: bytes):
    """把字节块包成异步迭代器。

    httpx 异步流式路径要求 resp.stream 是 AsyncIterable，
    传同步 iter() 会在 transport 层直接断言失败。
    """

    async def gen():
        for c in chunks:
            yield c

    return gen()


def _delta_event(content: str) -> str:
    return f'data: {{"choices":[{{"delta":{{"content":"{content}"}}}}]}}'


def _empty_delta_event() -> str:
    return 'data: {"choices":[{"delta":{}}]}'


async def _collect(agen) -> list[str]:
    return [chunk async for chunk in agen]


class TestStreamChatSuccess:
    @respx.mock
    async def test_yields_deltas_in_order(self):
        body = _sse(_delta_event("你好"), _delta_event("！"), "data: [DONE]")
        respx.post(CHAT_URL).respond(200, content=_aiter(body))

        chunks = await _collect(stream_chat([{"role": "user", "content": "hi"}]))

        assert chunks == ["你好", "！"]

    @respx.mock
    async def test_skips_empty_delta_and_done_marker(self):
        """delta 无 content 的块（如 role 块）和 [DONE] 标记本身不产出。

        注意实现语义：[DONE] 只是 continue 跳过该行，并不终止流，
        之后的 delta 仍正常 yield（真实服务一般 DONE 后即断开）。
        """
        body = _sse(
            _empty_delta_event(),
            _delta_event("ok"),
            _empty_delta_event(),
            "data: [DONE]",
            _delta_event("after-done"),
        )
        respx.post(CHAT_URL).respond(200, content=_aiter(body))

        chunks = await _collect(stream_chat([]))

        assert chunks == ["ok", "after-done"]

    @respx.mock
    async def test_ignores_non_data_lines(self):
        """注释行（: keep-alive）和空行直接跳过。"""
        body = _sse(": keep-alive", _delta_event("a"), "")
        respx.post(CHAT_URL).respond(200, content=_aiter(body))

        chunks = await _collect(stream_chat([]))

        assert chunks == ["a"]

    @respx.mock
    async def test_chunk_boundary_decoding(self):
        """字节流在 JSON 中间被切断，增量解码器应正确拼接。

        对应真实网络里 TCP 分包的场景。
        """
        body = _sse(_delta_event("你好"), _delta_event("世界"), "data: [DONE]")
        cut = len(body) // 2  # 在 JSON 中间切开
        respx.post(CHAT_URL).respond(200, content=_aiter(body[:cut], body[cut:]))

        chunks = await _collect(stream_chat([]))

        assert chunks == ["你好", "世界"]

    @respx.mock
    async def test_request_payload(self):
        route = respx.post(CHAT_URL).respond(200, content=_aiter(b"data: [DONE]\n\n"))
        messages = [{"role": "user", "content": "hi"}]

        await _collect(stream_chat(messages))

        import json

        body = json.loads(route.calls.last.request.content)
        assert body["model"] == settings.chat_model
        assert body["messages"] == messages
        assert body["stream"] is True


class TestStreamChatErrors:
    """HTTP 状态码 → 用户可读的 LLMServiceError。"""

    @respx.mock
    async def test_401_auth_failed(self):
        respx.post(CHAT_URL).respond(401, json={"error": "unauthorized"})

        with pytest.raises(LLMServiceError, match="鉴权失败"):
            await _collect(stream_chat([]))

    @respx.mock
    async def test_429_rate_limited(self):
        respx.post(CHAT_URL).respond(429, json={"error": "rate limited"})

        with pytest.raises(LLMServiceError, match="过于频繁"):
            await _collect(stream_chat([]))

    @respx.mock
    async def test_500_generic_status(self):
        respx.post(CHAT_URL).respond(500, json={"error": "boom"})

        with pytest.raises(LLMServiceError, match="状态码 500"):
            await _collect(stream_chat([]))

    @respx.mock
    async def test_timeout_mapped(self):
        respx.post(CHAT_URL).mock(side_effect=httpx.ReadTimeout("timeout"))

        with pytest.raises(LLMServiceError, match="超时"):
            await _collect(stream_chat([]))

    @respx.mock
    async def test_connect_error_mapped(self):
        respx.post(CHAT_URL).mock(side_effect=httpx.ConnectError("refused"))

        with pytest.raises(LLMServiceError, match="无法连接"):
            await _collect(stream_chat([]))

    @respx.mock
    async def test_error_is_llm_service_error_subclass(self):
        """错误类型可被上层 except LLMServiceError 精确捕获。"""
        respx.post(CHAT_URL).respond(401)

        with pytest.raises(LLMServiceError) as exc_info:
            await _collect(stream_chat([]))

        assert "API Key" in exc_info.value.message
