"""测试 app.services.prompt 模块。

纯函数测试，不依赖 DB / Redis / 外部 API。
"""

from app.services.prompt import SYSTEM_PROMPT, _MAX_CONTEXT_CHARS, build_messages


class TestBuildMessages:
    def test_basic_no_history(self):
        """无历史: system + user = 2 条消息"""
        messages = build_messages("什么是 RAG?", ["chunk1 content", "chunk2 content"])
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == SYSTEM_PROMPT
        assert messages[1]["role"] == "user"
        assert "什么是 RAG?" in messages[1]["content"]
        assert "chunk1 content" in messages[1]["content"]
        assert "chunk2 content" in messages[1]["content"]

    def test_with_history(self):
        """有历史: system + history + user"""
        history = [
            {"role": "user", "content": "之前的提问"},
            {"role": "assistant", "content": "之前的回答"},
        ]
        messages = build_messages("新问题", ["context"], history=history)
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[1] == {"role": "user", "content": "之前的提问"}
        assert messages[2] == {"role": "assistant", "content": "之前的回答"}
        assert messages[3]["role"] == "user"
        assert "新问题" in messages[3]["content"]

    def test_empty_history_same_as_none(self):
        """history=[] 等同于 history=None"""
        messages1 = build_messages("q", ["c"], history=None)
        messages2 = build_messages("q", ["c"], history=[])
        assert messages1 == messages2

    def test_empty_chunks(self):
        """空 chunks 列表: context 为空，但仍生成 user 消息"""
        messages = build_messages("question", [])
        assert len(messages) == 2
        assert messages[1]["role"] == "user"
        assert "question" in messages[1]["content"]
        # context 部分应该为空
        assert "【参考资料】" in messages[1]["content"]

    def test_truncation_when_exceeding_max_chars(self):
        """chunks 总字符数超过 _MAX_CONTEXT_CHARS 时，后面的 chunk 被丢弃"""
        # 构造 chunks 使总长度超过 _MAX_CONTEXT_CHARS
        chunk_a = "a" * 2000  # 2000 chars
        chunk_b = "b" * 2000  # 2000 chars, 总计 4000 > 3000
        messages = build_messages("q", [chunk_a, chunk_b])
        user_content = messages[-1]["content"]
        # chunk_a 应该在（2000 < 3000），chunk_b 应该被丢弃（2000+2000=4000 > 3000）
        assert "aaaa" in user_content
        assert "bbbb" not in user_content

    def test_chunk_indexing(self):
        """chunk 前面有编号 [1], [2] ..."""
        messages = build_messages("q", ["first", "second"])
        user_content = messages[-1]["content"]
        assert "[1]" in user_content
        assert "[2]" in user_content

    def test_truncation_is_whole_chunk_not_partial(self):
        """超过阈值的 chunk 整块丢弃，不做部分截断"""
        chunk_a = "a" * 2900  # 刚好不到 3000
        chunk_b = "b" * 200  # 2900 + 200 = 3100 > 3000 → 整块丢
        messages = build_messages("q", [chunk_a, chunk_b])
        user_content = messages[-1]["content"]
        assert "[1]" in user_content
        assert "a" * 100 in user_content
        assert "[2]" not in user_content
        assert "b" * 100 not in user_content
