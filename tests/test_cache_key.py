"""测试 app.core.cache.build_cache_key 函数。

纯函数测试，不依赖 DB / Redis。
"""
from app.core.cache import build_cache_key


class TestBuildCacheKey:
    def test_basic(self):
        key = build_cache_key("docs:list", tenant=1, page=1, size=10)
        # sorted by key name: page < size < tenant
        assert key == "docs:list:page=1:size=10:tenant=1"

    def test_none_values_skipped(self):
        key = build_cache_key("docs:list", tenant=1, page=None)
        assert key == "docs:list:tenant=1"

    def test_all_none(self):
        key = build_cache_key("docs:list", page=None, size=None)
        assert key == "docs:list"

    def test_no_extra_parts(self):
        key = build_cache_key("docs:list")
        assert key == "docs:list"

    def test_sorted_alphabetically(self):
        """参数按 key 名字母序排列，不依赖传入顺序"""
        key1 = build_cache_key("p", zebra=1, apple=2, mango=3)
        key2 = build_cache_key("p", mango=3, zebra=1, apple=2)
        assert key1 == key2
        assert key1 == "p:apple=2:mango=3:zebra=1"

    def test_string_values(self):
        key = build_cache_key("docfiles:list", tenant=5, status="pending")
        assert key == "docfiles:list:status=pending:tenant=5"

    def test_zero_and_false_not_skipped(self):
        """0 和 False 不是 None，应该出现在 key 里"""
        key = build_cache_key("p", flag=False, count=0)
        assert "count=0" in key
        assert "flag=False" in key
