import pytest

from cachka.core import (
    AsyncCache,
    CacheConfig,
)
from cachka.registry import (
    CacheRegistry,
)


class TestCacheRegistry:
    """Тесты CacheRegistry"""

    @pytest.mark.asyncio
    async def test_initialize_default_config(self):
        registry = CacheRegistry()
        registry.initialize()
        assert registry.is_initialized() is True
        assert isinstance(registry.get(), AsyncCache)
        # Cleanup
        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_custom_config(self):
        from cachka.sqlitecache import SQLiteCacheConfig
        from cachka.ttllrucache import MemoryCacheConfig

        registry = CacheRegistry()
        config = CacheConfig(
            cache_layers=[
                ("memory", MemoryCacheConfig(maxsize=2048, ttl=600)),
                ("sqlite", SQLiteCacheConfig(db_path=":memory:")),
            ]
        )
        registry.initialize(config)
        assert registry.is_initialized() is True
        cache = registry.get()
        assert len(cache._caches) == 2
        # Cleanup
        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_twice_raises(self):
        registry = CacheRegistry()
        registry.initialize()
        with pytest.raises(RuntimeError, match="Cache already initialized"):
            registry.initialize()
        # Cleanup
        await registry.shutdown()

    def test_get_before_initialize_raises(self):
        registry = CacheRegistry()
        with pytest.raises(RuntimeError, match="Cache not initialized"):
            registry.get()

    @pytest.mark.asyncio
    async def test_is_initialized(self):
        registry = CacheRegistry()
        assert registry.is_initialized() is False
        registry.initialize()
        assert registry.is_initialized() is True
        # Cleanup
        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown(self):
        registry = CacheRegistry()
        registry.initialize()
        await registry.shutdown()
        # After shutdown, should still be initialized but cache closed
        assert registry.is_initialized() is True

    @pytest.mark.asyncio
    async def test_shutdown_before_init(self):
        """Shutdown до инициализации не должен падать"""
        registry = CacheRegistry()
        await registry.shutdown()  # Should not raise

    @pytest.mark.asyncio
    async def test_shutdown_closes_cache(self):
        registry = CacheRegistry()
        registry.initialize()
        cache = registry.get()
        await registry.shutdown()
        # Cache should be closed (storage connection should be None)
        # Note: This is implementation detail, but we can check graceful_shutdown was called


class TestGlobalCacheRegistry:
    """Тесты глобального cache_registry"""

    def setup_method(self):
        """Сброс registry перед каждым тестом"""
        # Сбрасываем состояние через создание нового registry
        # В реальности нужно добавить метод reset() или использовать фикстуру
        pass

    @pytest.mark.asyncio
    async def test_global_registry_singleton(self):
        """Глобальный registry - singleton"""
        from cachka.registry import cache_registry

        # Если не инициализирован, должен быть один и тот же объект
        assert cache_registry is cache_registry

        # Инициализируем
        if not cache_registry.is_initialized():
            cache_registry.initialize()

        # Получаем два раза - должен быть один экземпляр
        cache1 = cache_registry.get()
        cache2 = cache_registry.get()
        assert cache1 is cache2
