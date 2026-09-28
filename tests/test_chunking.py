"""测试 app.services.chunking 模块。

纯函数测试，不依赖 DB / Redis / 外部 API。
"""
from app.services.chunking import (
    _split_into_paragraphs,
    _split_long_paragraph,
    chunk_text,
)


# ===== _split_into_paragraphs =====

class TestSplitIntoParagraphs:
    def test_normal_paragraphs(self):
        text = "para1\n\npara2\n\npara3"
        result = _split_into_paragraphs(text)
        assert result == ["para1", "para2", "para3"]

    def test_empty_text(self):
        assert _split_into_paragraphs("") == []

    def test_single_paragraph(self):
        text = "just one paragraph"
        result = _split_into_paragraphs(text)
        assert result == ["just one paragraph"]

    def test_code_block_not_split(self):
        """代码块内部的空行不会被当作段落分隔符"""
        text = "intro\n\n```python\nx = 1\n\ny = 2\n```\n\nafter"
        result = _split_into_paragraphs(text)
        assert result == ["intro", "```python\nx = 1\n\ny = 2\n```", "after"]

    def test_strips_empty_paragraphs(self):
        """纯空白段落被过滤"""
        text = "para1\n\n  \n\npara2"
        result = _split_into_paragraphs(text)
        assert result == ["para1", "para2"]


# ===== _split_long_paragraph =====

class TestSplitLongParagraph:
    def test_basic_split(self):
        """超长段落按 chunk_size 切分，带 overlap"""
        text = "a" * 1200
        chunks = _split_long_paragraph(text, chunk_size=500, overlap=50)
        # 1200 / 500 → 第一块 [0:500], 第二块 [450:950], 第三块 [900:1200]
        assert len(chunks) == 3
        assert len(chunks[0]) == 500
        assert chunks[0] == "a" * 500
        assert chunks[1] == "a" * 500
        assert len(chunks[2]) == 300

    def test_exact_fit(self):
        """段落长度刚好等于 chunk_size，只切一块"""
        text = "x" * 500
        chunks = _split_long_paragraph(text, chunk_size=500, overlap=50)
        assert len(chunks) == 1
        assert chunks[0] == "x" * 500

    def test_no_overlap(self):
        """overlap=0 时不重叠"""
        text = "abcdefghij"  # 10 chars
        chunks = _split_long_paragraph(text, chunk_size=4, overlap=0)
        assert chunks == ["abcd", "efgh", "ij"]


# ===== chunk_text（集成）=====

class TestChunkText:
    def test_empty_text(self):
        assert chunk_text("") == []

    def test_short_text_one_chunk(self):
        """短文本不切块"""
        text = "This is a short paragraph."
        result = chunk_text(text, chunk_size=500, overlap=50)
        assert len(result) == 1
        assert result[0] == "This is a short paragraph."

    def test_multiple_paragraphs_merge(self):
        """多个小段落合并到接近 chunk_size"""
        para1 = "a" * 200
        para2 = "b" * 200
        para3 = "c" * 200
        text = f"{para1}\n\n{para2}\n\n{para3}"
        result = chunk_text(text, chunk_size=500, overlap=50)
        # 200 + 2(\n\n) + 200 = 402 ≤ 500，第三段加入后 604 > 500
        # 所以前两段合并，第三段单独
        assert len(result) == 2
        assert para1 in result[0]
        assert para2 in result[0]
        assert result[1] == para3

    def test_long_paragraph_triggers_sliding_window(self):
        """单个超长段落触发滑动窗口切块"""
        text = "x" * 1200
        result = chunk_text(text, chunk_size=500, overlap=50)
        assert len(result) == 3

    def test_code_block_preserved_as_single_chunk(self):
        """代码块作为整体段落，不被内部空行拆散"""
        code = "```python\nx = 1\n\ny = 2\n```"
        text = f"intro\n\n{code}"
        result = chunk_text(text, chunk_size=500, overlap=50)
        # 两段都能放进一个 chunk（intro + code < 500）
        assert len(result) == 1
        assert "intro" in result[0]
        assert "```python" in result[0]
        assert "y = 2" in result[0]
