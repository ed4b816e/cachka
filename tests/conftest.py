"""
Общие фикстуры для всех тестов
"""
import pytest
import asyncio
from cachka import cache_registry, CacheConfig
from cachka.sqlitecache import SQLiteCacheConfig


@pytest.fixture(scope="function")
def cache_config():
    """Базовая конфигурация кэша для тестов"""
    return CacheConfig(
        cache_layers=[
            "memory",
            ("sqlite", SQLiteCacheConfig(db_path=":memory:"))
        ],
        vacuum_interval=None,
        cleanup_on_start=False,
        enable_metrics=False
    )


@pytest.fixture(scope="function")
async def initialized_cache(cache_config):
    """Инициализированный кэш для тестов"""
    # Сбрасываем перед инициализацией
    if cache_registry.is_initialized():
        try:
            await cache_registry.shutdown()
        except:
            pass
    
    cache_registry.initialize(cache_config)
    yield cache_registry.get()
    
    # Cleanup после теста
    if cache_registry.is_initialized():
        try:
            await cache_registry.shutdown()
        except:
            pass


@pytest.fixture(scope="function", autouse=True)
async def reset_cache_registry_after_test():
    """Автоматически сбрасывает registry после каждого теста"""
    yield
    # Cleanup после теста
    if cache_registry.is_initialized():
        try:
            await cache_registry.shutdown()
        except:
            pass
        # Сбрасываем состояние
        cache_registry.reset()

