import threading
from typing import Optional

from .core import (
    AsyncCache,
    CacheConfig,
)


class CacheRegistry:
    def __init__(self):
        self._instance: Optional[AsyncCache] = None
        self._lock = threading.Lock()
        self._initialized = False

    def initialize(self, config: Optional[CacheConfig] = None):
        with self._lock:
            if self._initialized:
                raise RuntimeError("Cache already initialized")
            if config is None:
                # Дефолтная конфигурация: memory + sqlite
                from cachka.sqlitecache import SQLiteCacheConfig

                config = CacheConfig(
                    cache_layers=[
                        "memory",
                        ("sqlite", SQLiteCacheConfig(db_path="cache.db")),
                    ]
                )
            self._instance = AsyncCache(config)
            self._initialized = True

    def get(self) -> AsyncCache:
        if not self._initialized:
            raise RuntimeError(
                "Cache not initialized. Call `cache_registry.initialize()` during app startup."
            )
        return self._instance

    def is_initialized(self) -> bool:
        return self._initialized

    async def shutdown(self):
        if self._initialized and self._instance:
            await self._instance.graceful_shutdown()

    def reset(self):
        """Сброс состояния registry (для тестов)"""
        with self._lock:
            self._initialized = False
            self._instance = None


# Global singleton
cache_registry = CacheRegistry()
