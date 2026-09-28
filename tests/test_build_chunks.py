"""测试 app.services.chunking.build_chunk_records —— 切块 + 批量向量化 + 记录构造。

get_embeddings 在 import 时已绑定到 chunking 模块命名空间，
所以 patch 的是 app.services.chunking.get_embeddings（不是定义处）。
纯内存操作，不碰 DB。
"""
import pytest

from app.services.chunking import build_chunk_records, chunk_text

FAKE_VECTOR = [0.1, 0.2, 0.3]


@pytest.fixture
def fake_embeddings(monkeypatch):
    """替换成确定性假实现：每个 chunk 返回同一个向量，并记录调用入参。"""
    calls: list[list[str]] = []

    async def _fake(texts: list[str]) -> list[list[float]]:
        calls.append(list(texts))
        return [list(FAKE_VECTOR) for _ in texts]

    monkeypatch.setattr("app.services.chunking.get_embeddings", _fake)
    return calls


class TestBuildChunkRecords:
    async def test_empty_text_returns_empty(self, fake_embeddings):
        assert await build_chunk_records(1, 1, "") == []
        assert fake_embeddings == []  # 没有切块就不调 embedding

    async def test_records_match_chunks(self, fake_embeddings):
        text = "第一段。\n\n第二段。\n\n第三段。"
        expected_chunks = chunk_text(text)

        records = await build_chunk_records(tenant_id=7, document_id=42, cleaned_text=text)

        assert len(records) == len(expected_chunks) > 0
        for idx, (record, chunk) in enumerate(zip(records, expected_chunks)):
            assert record.chunk_index == idx
            assert record.content == chunk
            assert record.char_count == len(chunk)
            assert record.embedding == FAKE_VECTOR
            assert record.tenant_id == 7
            assert record.document_id == 42

    async def test_embeddings_called_with_exact_chunks(self, fake_embeddings):
        text = "alpha\n\nbeta"
        chunks = chunk_text(text)

        await build_chunk_records(1, 1, text)

        assert fake_embeddings == [chunks]  # 一次批量调用，入参就是切块结果

    async def test_long_paragraph_multiple_chunks(self, fake_embeddings):
        """超过 chunk_size 的单段落触发滑动窗口，产出多块且索引连续。"""
        text = "长" * 1200

        records = await build_chunk_records(1, 1, text)

        assert len(records) > 1
        assert [r.chunk_index for r in records] == list(range(len(records)))
        assert all(r.embedding == FAKE_VECTOR for r in records)
