import functools
import inspect
from logging import getLogger
from typing import Callable

from .constants import Intervals
from .core import CacheConfig
from .interface import ICache
from .rate_limiter import (
    MemoryRateLimiter,
    RateLimitExceeded,
    RateLimiterConfig,
)
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
    from .rate_limiter import RateLimiter

    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False
    RedisCacheAdapter = None
    RedisCacheConfig = None
    RateLimiter = None

__all__ = [
    "cached",
    "rate_limited",
    "cache_registry",
    "CacheConfig",
    "MemoryCacheConfig",
    "SQLiteCacheConfig",
    "ICache",
    "TTLLRUCacheAdapter",
    "SQLiteStorageAdapter",
    "Intervals",
    "RateLimiterConfig",
    "RateLimitExceeded",
    "MemoryRateLimiter",
]

if _HAS_REDIS:
    __all__.extend(
        [
            "RedisCacheConfig",
            "RedisCacheAdapter",
            "RateLimiter",
        ]
    )


logger = getLogger(__name__)


def cached(
    ttl: int = Intervals.FIVE_MINUTES,
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


def rate_limited(
    tag: str,
    *,
    wait: bool = True,
    identifier: str = "default",
):
    """
    Decorator that enforces a named rate limiter profile.

    Profiles must be registered first::

        cache = cache_registry.get()
        cache.init_rate_limiter(
            {"external_api": RateLimiterConfig(max_requests=60, window_seconds=60)},
            backend="redis",
            redis=RedisCacheConfig(host="localhost", port=6379),
        )

        @rate_limited(tag="external_api")
        async def fetch():
            ...

    Args:
        tag: Profile name from init_rate_limiter(...)
        wait: If True, wait until a slot is free (or timeout). If False, check once.
        identifier: Extra bucket id inside the tag (default: "default")

    Raises:
        RateLimitExceeded: when the request is not allowed
        RuntimeError: if cache / rate limiter is not initialized
        KeyError: if tag is unknown
        TypeError: if used on a sync function
    """

    def decorator(func: Callable):
        if not inspect.iscoroutinefunction(func):
            raise TypeError(
                "@rate_limited currently supports async functions only"
            )

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache = cache_registry.get()
            limiter = cache.get_rate_limiter(tag)

            if wait:
                allowed = await limiter.wait_until_allowed(identifier=identifier)
            else:
                allowed = await limiter.is_request_allowed(identifier=identifier)

            if not allowed:
                raise RateLimitExceeded(tag=tag, identifier=identifier)

            return await func(*args, **kwargs)

        return wrapper

    return decorator
