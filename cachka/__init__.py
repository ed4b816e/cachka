import asyncio
import inspect
from typing import Callable

from logging import getLogger

from .registry import cache_registry
from .core import CacheConfig
from .utils import make_cache_key


logger = getLogger(__name__)


def cached(ttl: int = 300, ignore_self: bool = False):
    def decorator(func: Callable):
        if inspect.iscoroutinefunction(func):
            # Async function
            async def wrapper(*args, **kwargs):
                cache = cache_registry.get()
                key_args = args[1:] if ignore_self and args else args
                key = make_cache_key(func.__name__, key_args, kwargs)
                cached_val = await cache.get(key)
                if cached_val is not None:
                    return cached_val
                result = await func(*args, **kwargs)
                await cache.set(key, result, ttl)
                return result
            return wrapper

        else:
            # Sync function
            def wrapper(*args, **kwargs):
                cache = cache_registry.get()
                key_args = args[1:] if ignore_self and args else args
                key = make_cache_key(func.__name__, key_args, kwargs)

                # Try L1
                l1_val = None
                with cache.l1_lock:
                    if key in cache.l1_cache:
                        l1_val = cache.l1_cache[key]
                if l1_val is not None:
                    return l1_val

                loop = asyncio.get_running_loop()
                future = asyncio.run_coroutine_threadsafe(cache.get(key), loop)
                cached_val = future.result()

                if cached_val is not None:
                    return cached_val

                result = func(*args, **kwargs)

                loop = asyncio.get_running_loop()
                future = asyncio.run_coroutine_threadsafe(cache.set(key, result, ttl), loop)
                future.result()

                return result
            return wrapper
    return decorator


__all__ = ["cached", "cache_registry", "CacheConfig"]