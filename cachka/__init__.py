import inspect
import functools
from typing import Callable

from logging import getLogger

from .registry import cache_registry
from .core import CacheConfig
from .utils import prepare_cache_key


logger = getLogger(__name__)


def cached(ttl: int = 300, ignore_self: bool = False):
    def decorator(func: Callable):
        if inspect.iscoroutinefunction(func):
            # Async function
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                cache = cache_registry.get()
                key = prepare_cache_key(func, args, kwargs, ignore_self)
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
                key = prepare_cache_key(func, args, kwargs, ignore_self)
                cached_val = cache.get_sync(key)
                if cached_val is not None:
                    return cached_val
                result = func(*args, **kwargs)
                cache.set_sync(key, result, ttl)
                return result
            return wrapper
    return decorator


__all__ = ["cached", "cache_registry", "CacheConfig"]