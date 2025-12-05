import functools
import inspect
from logging import getLogger
from typing import Callable

from .core import CacheConfig
from .interface import ICache
from .registry import cache_registry
from .sqlitecache import (
    SQLiteCacheConfig,
    SQLiteStorageAdapter,
)
from .ttllrucache import (
    MemoryCacheConfig,
    TTLLRUCacheAdapter,
)
from .utils import prepare_cache_key

# Redis - опциональная зависимость
try:
    from .rediscache import (
        RedisCacheAdapter,
        RedisCacheConfig,
    )

    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False
    RedisCacheAdapter = None
    RedisCacheConfig = None

__all__ = [
    "cached",
    "cache_registry",
    "CacheConfig",
    "MemoryCacheConfig",
    "SQLiteCacheConfig",
    "ICache",
    "TTLLRUCacheAdapter",
    "SQLiteStorageAdapter",
]

if _HAS_REDIS:
    __all__.extend(["RedisCacheConfig", "RedisCacheAdapter"])


logger = getLogger(__name__)


def cached(
    ttl: int = 300,
    ignore_self: bool = False,
    simplified_self_serialization: bool = False,
):
    """
    Декоратор для кэширования результатов функций.

    Args:
        ttl: Время жизни кэша в секундах (по умолчанию 300)
        ignore_self: [DEPRECATED] Используйте simplified_self_serialization вместо этого.
                        Если True, исключает self из ключа кэша и использует имя класса.
        simplified_self_serialization: Если True, использует упрощенную сериализацию self:
                                        исключает self из ключа кэша и использует имя класса вместо него.
                                        Полезно для методов, где self плохо сериализуется.
                                        Применяется только если функция является методом класса (определяется автоматически).

    Returns:
        Декорированная функция с кэшированием
    """

    def decorator(func: Callable):
        if inspect.iscoroutinefunction(func):
            # Async function
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                cache = cache_registry.get()
                key = prepare_cache_key(
                    func,
                    args,
                    kwargs,
                    ignore_self=ignore_self,
                    simplified_self_serialization=simplified_self_serialization,
                )
                cached_val = await cache.get(key)
                if cached_val is not None:
                    return cached_val
                result = await func(*args, **kwargs)
                await cache.set(key, result, ttl)
                return result

            return wrapper

        else:
            # Sync function
            @functools.wraps(func)
            def wrapper(*args, **kwargs):
                cache = cache_registry.get()
                key = prepare_cache_key(
                    func,
                    args,
                    kwargs,
                    ignore_self=ignore_self,
                    simplified_self_serialization=simplified_self_serialization,
                )
                cached_val = cache.get_sync(key)
                if cached_val is not None:
                    return cached_val
                result = func(*args, **kwargs)
                cache.set_sync(key, result, ttl)
                return result

            return wrapper

    return decorator


# __all__ определяется динамически в зависимости от наличия Redis
