"""测试 app.services.extraction 模块。

纯函数测试，不依赖 DB / Redis / 外部 API。
"""

import pytest

from app.models.document_file import SourceType
from app.services.extraction import clean_text, extract_text

# ===== clean_text =====


class TestCleanText:
    def test_normalize_crlf(self):
        """Windows 换行 \\r\\n 统一成 \\n"""
        text = "line1\r\nline2\r\nline3"
        result = clean_text(text)
        assert result == "line1\nline2\nline3"

    def test_normalize_cr(self):
        """旧 Mac 换行 \\r 统一成 \\n"""
        text = "line1\rline2"
        result = clean_text(text)
        assert result == "line1\nline2"

    def test_strip_trailing_whitespace(self):
        """行尾空白被去除"""
        text = "line1   \nline2\t"
        result = clean_text(text)
        assert result == "line1\nline2"

    def test_compress_multiple_blank_lines(self):
        """3 个以上连续空行压缩成 1 个空行（2 个 \\n）"""
        text = "para1\n\n\n\n\npara2"
        result = clean_text(text)
        assert result == "para1\n\npara2"

    def test_two_blank_lines_preserved(self):
        """2 个连续空行（正常的段落分隔）不压缩"""
        text = "para1\n\npara2"
        result = clean_text(text)
        assert result == "para1\n\npara2"

    def test_strip_outer_whitespace(self):
        """首尾空白被 strip"""
        text = "  \n hello \n  "
        result = clean_text(text)
        assert result == "hello"

    def test_empty_string(self):
        assert clean_text("") == ""

    def test_only_whitespace(self):
        assert clean_text("   \n\n  \t  ") == ""


# ===== _extract_markdown_text =====


class TestExtractMarkdownText:
    def test_valid_utf8(self):
        raw = "你好，世界".encode()
        result = extract_text(SourceType.MARKDOWN, raw)
        assert result == "你好，世界"

    def test_plain_ascii(self):
        raw = b"# Hello\n\nThis is markdown."
        result = extract_text(SourceType.MARKDOWN, raw)
        assert result == "# Hello\n\nThis is markdown."

    def test_invalid_utf8_raises(self):
        with pytest.raises(ValueError, match="not valid UTF-8"):
            extract_text(SourceType.MARKDOWN, b"\xff\xfe\x00\x00")


# ===== extract_text dispatch =====


class TestExtractTextDispatch:
    def test_markdown_dispatch(self):
        raw = b"hello"
        result = extract_text(SourceType.MARKDOWN, raw)
        assert result == "hello"

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="Unsupported source_type"):
            extract_text("unknown", b"hello")
