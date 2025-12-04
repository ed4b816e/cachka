import asyncio
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

                # Try L1
                l1_val = None
                with cache.l1_lock:
                    if key in cache.l1_cache:
                        l1_val = cache.l1_cache[key]
                if l1_val is not None:
                    return l1_val

                # Get or create event loop for async operations
                try:
                    loop = asyncio.get_running_loop()
                    # Running loop exists, use run_coroutine_threadsafe
                    future = asyncio.run_coroutine_threadsafe(cache.get(key), loop)
                    cached_val = future.result()
                    
                    if cached_val is not None:
                        return cached_val
                    
                    result = func(*args, **kwargs)
                    
                    future = asyncio.run_coroutine_threadsafe(cache.set(key, result, ttl), loop)
                    future.result()
                except RuntimeError:
                    # No running loop, use asyncio.run for isolated execution
                    async def _get_cached():
                        return await cache.get(key)
                    
                    cached_val = asyncio.run(_get_cached())
                    
                    if cached_val is not None:
                        return cached_val
                    
                    result = func(*args, **kwargs)
                    
                    async def _set_cached():
                        await cache.set(key, result, ttl)
                    
                    asyncio.run(_set_cached())

                return result
            return wrapper
    return decorator


__all__ = ["cached", "cache_registry", "CacheConfig"]