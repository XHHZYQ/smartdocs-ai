"""测试 app.services.embedding.get_embeddings —— 外部 HTTP mock。

对应 Fastify 生态里的 nock / msw：respx 拦截 httpx 请求，
不真正调用 SiliconFlow API，测试完全确定性、无网络开销。
"""
import json

import httpx
import pytest
import respx

from app.core.config import settings
from app.services.embedding import get_embeddings

EMBEDDINGS_URL = f"{settings.embedding_base_url}/embeddings"


def _api_response(vectors: list[list[float]]) -> dict:
    """按 OpenAI 兼容格式包装响应体：{"data": [{"embedding": [...]}, ...]}"""
    return {"data": [{"embedding": v} for v in vectors]}


def _echo_by_input(request: httpx.Request) -> httpx.Response:
    """确定性 side_effect：每个输入文本返回 [len(text), 0, 0]，
    用于验证跨批次后结果顺序与输入一一对应。"""
    body = json.loads(request.content)
    vectors = [[float(len(t)), 0.0, 0.0] for t in body["input"]]
    return httpx.Response(200, json=_api_response(vectors))


class TestGetEmbeddings:
    @respx.mock
    async def test_single_batch_returns_in_order(self):
        vec_a = [0.1, 0.2, 0.3]
        vec_b = [0.4, 0.5, 0.6]
        respx.post(EMBEDDINGS_URL).respond(json=_api_response([vec_a, vec_b]))

        result = await get_embeddings(["你好", "世界"])

        assert result == [vec_a, vec_b]

    async def test_empty_input_skips_http(self):
        with respx.mock:
            route = respx.post(EMBEDDINGS_URL).respond(json=_api_response([]))
            result = await get_embeddings([])

        assert result == []
        assert route.called is False  # 空输入直接短路，不发请求

    @respx.mock
    async def test_batches_by_configured_size(self, monkeypatch):
        """5 条文本、batch_size=2 → 3 次请求，结果顺序不变。"""
        monkeypatch.setattr(settings, "embedding_batch_size", 2)
        texts = [f"chunk-{i}" for i in range(5)]
        route = respx.post(EMBEDDINGS_URL).mock(side_effect=_echo_by_input)

        result = await get_embeddings(texts)

        assert len(route.calls) == 3
        assert len(result) == 5
        # 顺序保持：第 i 个结果对应第 i 个输入（用 len 做指纹）
        assert [v[0] for v in result] == [float(len(t)) for t in texts]

    @respx.mock
    async def test_request_payload_and_auth_header(self):
        route = respx.post(EMBEDDINGS_URL).respond(json=_api_response([[1.0]]))

        await get_embeddings(["hello"])

        request = route.calls.last.request
        body = json.loads(request.content)
        assert body["model"] == settings.embedding_model
        assert body["input"] == ["hello"]
        assert request.headers["Authorization"] == f"Bearer {settings.embedding_api_key}"

    @respx.mock
    async def test_http_error_propagates(self):
        """任一批失败直接抛 HTTPStatusError，由上层 arq 任务决定重试。"""
        respx.post(EMBEDDINGS_URL).respond(status_code=500, json={"error": "boom"})

        with pytest.raises(httpx.HTTPStatusError):
            await get_embeddings(["text"])

    @respx.mock
    async def test_timeout_propagates(self):
        respx.post(EMBEDDINGS_URL).mock(side_effect=httpx.ReadTimeout("timeout"))

        with pytest.raises(httpx.TimeoutException):
            await get_embeddings(["text"])
