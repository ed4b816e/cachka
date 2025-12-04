import pytest
from cachka.utils import make_cache_key


class TestMakeCacheKey:
    """Тесты генерации ключей кэша"""

    def test_key_generation_deterministic(self):
        """Ключ должен быть детерминированным"""
        key1 = make_cache_key("func", (1, 2), {"a": 3})
        key2 = make_cache_key("func", (1, 2), {"a": 3})
        assert key1 == key2

    def test_key_different_for_different_args(self):
        """Разные аргументы = разные ключи"""
        key1 = make_cache_key("func", (1,), {})
        key2 = make_cache_key("func", (2,), {})
        assert key1 != key2

    def test_key_same_for_same_args(self):
        """Одинаковые аргументы = одинаковый ключ"""
        key1 = make_cache_key("func", (1, 2, 3), {"x": 10, "y": 20})
        key2 = make_cache_key("func", (1, 2, 3), {"x": 10, "y": 20})
        assert key1 == key2

    def test_key_handles_kwargs_order(self):
        """Порядок kwargs не важен"""
        key1 = make_cache_key("func", (), {"a": 1, "b": 2})
        key2 = make_cache_key("func", (), {"b": 2, "a": 1})
        assert key1 == key2  # sorted(kwargs.items()) делает порядок неважным

    def test_key_different_functions(self):
        """Разные функции = разные ключи"""
        key1 = make_cache_key("func1", (1,), {})
        key2 = make_cache_key("func2", (1,), {})
        assert key1 != key2

    def test_key_with_none(self):
        """Ключ с None значениями"""
        key1 = make_cache_key("func", (None,), {"x": None})
        key2 = make_cache_key("func", (None,), {"x": None})
        assert key1 == key2

    def test_key_with_complex_objects(self):
        """Сложные объекты в аргументах"""
        obj1 = {"nested": [1, 2, 3]}
        obj2 = {"nested": [1, 2, 3]}
        key1 = make_cache_key("func", (obj1,), {})
        key2 = make_cache_key("func", (obj2,), {})
        assert key1 == key2

    def test_key_with_unicode(self):
        """Unicode в аргументах"""
        key1 = make_cache_key("func", ("тест",), {"ключ": "значение"})
        key2 = make_cache_key("func", ("тест",), {"ключ": "значение"})
        assert key1 == key2

    def test_key_length(self):
        """Длина ключа (SHA256 = 64 hex chars)"""
        key = make_cache_key("func", (1, 2, 3), {"a": "b"})
        assert len(key) == 64  # SHA256 hex digest length
        assert all(c in '0123456789abcdef' for c in key)

    def test_key_empty_args(self):
        """Пустые аргументы"""
        key1 = make_cache_key("func", (), {})
        key2 = make_cache_key("func", (), {})
        assert key1 == key2

    def test_key_only_kwargs(self):
        """Только kwargs"""
        key1 = make_cache_key("func", (), {"x": 1, "y": 2})
        key2 = make_cache_key("func", (), {"y": 2, "x": 1})
        assert key1 == key2

    def test_key_only_args(self):
        """Только args"""
        key1 = make_cache_key("func", (1, 2, 3), {})
        key2 = make_cache_key("func", (1, 2, 3), {})
        assert key1 == key2

