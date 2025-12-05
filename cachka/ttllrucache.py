import time
import threading
import asyncio
import dataclasses
from collections import OrderedDict
from typing import Any, Optional, Callable, Awaitable
from contextlib import contextmanager, asynccontextmanager

from cachka.interface import ICache


# === Config ===

@dataclasses.dataclass
class MemoryCacheConfig:
    """Конфигурация для memory кэша (TTLLRUCache)"""
    maxsize: int = 1024
    ttl: int = 300
    shards: int = 8
    enable_metrics: bool = False
    name: str = "memory_cache"


# === Implementation ===

class TTLLRUCache:
    def __init__(
        self,
        maxsize: int = 1024,
        ttl: int = 300,
        shards: int = 8,
        enable_metrics: bool = False,
        name: str = "l1_cache",
    ):
        if maxsize <= 0:
            raise ValueError("maxsize must be > 0")
        if ttl <= 0:
            raise ValueError("ttl must be > 0")
        if shards <= 0:
            raise ValueError("shards must be > 0")

        # Распределяем maxsize по шардам
        # Если shards=1, то maxsize_per_shard = maxsize
        # Иначе гарантируем, что сумма >= maxsize, но каждый шард <= maxsize
        if shards == 1:
            self.maxsize_per_shard = maxsize
        else:
            # Вычисляем размер шарда, но ограничиваем его maxsize
            # чтобы один шард не мог содержать больше элементов, чем весь кэш
            calculated_size = maxsize // shards + 1
            self.maxsize_per_shard = min(calculated_size, maxsize)
        self.ttl = ttl
        self.shards = shards
        self.name = name
        self._is_async = False
        self._bg_task: Optional[asyncio.Task] = None

        # Create shards
        self._shards = [
            _LRUTTLShard(self.maxsize_per_shard, ttl, enable_metrics, name, i)
            for i in range(shards)
        ]

        # Detect async context on first use
        self._determine_mode()

    def _determine_mode(self):
        """Determine if we're in async context (best-effort)."""
        try:
            asyncio.get_running_loop()
            self._is_async = True
        except RuntimeError:
            self._is_async = False

    def _get_shard(self, key: str) -> '_LRUTTLShard':
        """Consistent shard selection."""
        return self._shards[hash(key) % self.shards]

    # === Sync API ===
    def get(self, key: str, default: Any = None) -> Any:
        shard = self._get_shard(key)
        return shard.get(key, default)

    def set(self, key: str, value: Any) -> None:
        shard = self._get_shard(key)
        shard.set(key, value)

    def delete(self, key: str) -> None:
        shard = self._get_shard(key)
        shard.delete(key)

    def touch(self, key: str) -> bool:
        """Extend TTL if exists."""
        shard = self._get_shard(key)
        return shard.touch(key)

    def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        """Atomic get-or-set (thread-safe)."""
        shard = self._get_shard(key)
        return shard.get_or_set(key, factory)

    def cleanup(self) -> int:
        """Force cleanup expired entries across all shards."""
        total = 0
        for shard in self._shards:
            total += shard.cleanup()
        return total

    def __len__(self) -> int:
        return sum(len(shard) for shard in self._shards)

    # === Async API ===
    async def get_async(self, key: str, default: Any = None) -> Any:
        shard = self._get_shard(key)
        return await shard.get_async(key, default)

    async def set_async(self, key: str, value: Any) -> None:
        shard = self._get_shard(key)
        await shard.set_async(key, value)

    async def delete_async(self, key: str) -> None:
        shard = self._get_shard(key)
        await shard.delete_async(key)

    async def touch_async(self, key: str) -> bool:
        shard = self._get_shard(key)
        return await shard.touch_async(key)

    async def get_or_set_async(
        self, key: str, factory: Callable[[], Awaitable[Any]]
    ) -> Any:
        shard = self._get_shard(key)
        return await shard.get_or_set_async(key, factory)

    async def start_background_cleanup(self, interval: int = 60):
        """Start async background cleanup task."""
        if not self._is_async:
            raise RuntimeError("Background cleanup requires async context")
        if self._bg_task is not None:
            raise RuntimeError("Background cleanup already started")

        async def _cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(interval)
                    await asyncio.get_running_loop().run_in_executor(
                        None, self.cleanup
                    )
                except asyncio.CancelledError:
                    break
                except Exception:
                    pass  # log in real app

        self._bg_task = asyncio.create_task(_cleanup_loop())

    async def stop_background_cleanup(self):
        """Stop background cleanup task."""
        if self._bg_task:
            self._bg_task.cancel()
            try:
                await self._bg_task
            except asyncio.CancelledError:
                pass
            self._bg_task = None

    def __getitem__(self, key, default=None):
        return self.get(key=key, default=default)

    def __setitem__(self, key, value):
        self.set(key=key, value=value)

    def __contains__(self, key: str) -> bool:
        shard = self._get_shard(key)
        return key in shard


class _LRUTTLShard:
    """Internal shard with its own lock and cache."""

    def __init__(self, maxsize: int, ttl: int, enable_metrics: bool, cache_name: str, shard_id: int):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache = OrderedDict()
        self._lock = threading.RLock()
        self._async_lock = None  # lazy init

        # Metrics (optional)
        self._metrics = None
        if enable_metrics:
            self._init_metrics(cache_name, shard_id)

    def _init_metrics(self, cache_name: str, shard_id: int):
        try:
            from prometheus_client import Counter, Histogram
            self._metrics = {
                "hits": Counter(
                    "cache_l1_hits_total",
                    "L1 cache hits",
                    ["cache", "shard"]
                ).labels(cache=cache_name, shard=str(shard_id)),
                "misses": Counter(
                    "cache_l1_misses_total",
                    "L1 cache misses",
                    ["cache", "shard"]
                ).labels(cache=cache_name, shard=str(shard_id)),
                "evictions": Counter(
                    "cache_l1_evictions_total",
                    "L1 cache evictions",
                    ["cache", "shard"]
                ).labels(cache=cache_name, shard=str(shard_id)),
            }
        except ImportError:
            self._metrics = None

    def _now(self) -> float:
        return time.time()

    def _is_expired(self, timestamp: float) -> bool:
        return self._now() - timestamp > self.ttl

    def _cleanup_expired(self) -> int:
        """Remove expired from head of LRU list."""
        removed = 0
        keys_to_remove = []
        for key, (_, ts) in self._cache.items():
            if self._is_expired(ts):
                keys_to_remove.append(key)
                removed += 1
            else:
                break  # OrderedDict is LRU-ordered
        for key in keys_to_remove:
            del self._cache[key]
        return removed

    @contextmanager
    def _sync_lock(self):
        with self._lock:
            yield

    @asynccontextmanager
    async def _async_lock_ctx(self):
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        async with self._async_lock:
            yield

    # === Sync methods ===
    def get(self, key: str, default: Any = None) -> Any:
        with self._sync_lock():
            self._cleanup_expired()
            if key in self._cache:
                value, ts = self._cache[key]
                if self._is_expired(ts):
                    del self._cache[key]
                    if self._metrics:
                        self._metrics["misses"].inc()
                    return default
                self._cache.move_to_end(key)
                if self._metrics:
                    self._metrics["hits"].inc()
                return value
            if self._metrics:
                self._metrics["misses"].inc()
            return default

    def set(self, key: str, value: Any) -> None:
        with self._sync_lock():
            now = self._now()
            # Если ключ уже существует, удаляем его сначала, чтобы гарантировать правильный порядок
            if key in self._cache:
                del self._cache[key]
            # Добавляем ключ в конец (most recently used)
            self._cache[key] = (value, now)
            evicted = 0
            while len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)
                evicted += 1
            if evicted and self._metrics:
                self._metrics["evictions"].inc(evicted)

    def delete(self, key: str) -> None:
        with self._sync_lock():
            self._cache.pop(key, None)

    def touch(self, key: str) -> bool:
        with self._sync_lock():
            if key in self._cache:
                value, _ = self._cache[key]
                self._cache[key] = (value, self._now())
                self._cache.move_to_end(key)
                return True
            return False

    def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        with self._sync_lock():
            self._cleanup_expired()
            if key in self._cache:
                value, ts = self._cache[key]
                if not self._is_expired(ts):
                    self._cache.move_to_end(key)
                    if self._metrics:
                        self._metrics["hits"].inc()
                    return value
            # Miss
            value = factory()
            self.set(key, value)
            if self._metrics:
                self._metrics["misses"].inc()
            return value

    def cleanup(self) -> int:
        with self._sync_lock():
            return self._cleanup_expired()

    def __len__(self) -> int:
        with self._sync_lock():
            self._cleanup_expired()
            return len(self._cache)

    def __contains__(self, key: str) -> bool:
        with self._sync_lock():
            return key in self._cache

    # === Async wrappers ===
    async def get_async(self, key: str, default: Any = None) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get, key, default)

    async def set_async(self, key: str, value: Any) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.set, key, value)

    async def delete_async(self, key: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.delete, key)

    async def touch_async(self, key: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.touch, key)

    async def get_or_set_async(
        self, key: str, factory: Callable[[], Awaitable[Any]]
    ) -> Any:
        # First, try to get
        existing = await self.get_async(key)
        if existing is not None:
            return existing
        # Compute in async
        value = await factory()
        await self.set_async(key, value)
        return value


# === Adapter ===

class TTLLRUCacheAdapter(ICache):
    """
    Адаптер для TTLLRUCache, реализующий интерфейс ICache.
    
    TTLLRUCache имеет свой собственный API (get/set для sync, get_async/set_async для async),
    этот адаптер оборачивает его для соответствия интерфейсу ICache.
    """
    
    def __init__(self, cache: TTLLRUCache):
        self._cache = cache
    
    async def get(self, key: str) -> Optional[Any]:
        """Асинхронное получение значения из кэша"""
        return await self._cache.get_async(key)
    
    async def set(self, key: str, value: Any, ttl: int) -> None:
        """
        Асинхронная установка значения в кэш.
        
        Примечание: TTLLRUCache использует глобальный TTL из конфигурации,
        параметр ttl здесь игнорируется для совместимости с интерфейсом.
        """
        await self._cache.set_async(key, value)
    
    def get_sync(self, key: str) -> Optional[Any]:
        """Синхронное получение значения из кэша"""
        return self._cache.get(key)
    
    def set_sync(self, key: str, value: Any, ttl: int) -> None:
        """
        Синхронная установка значения в кэш.
        
        Примечание: TTLLRUCache использует глобальный TTL из конфигурации,
        параметр ttl здесь игнорируется для совместимости с интерфейсом.
        """
        self._cache.set(key, value)
    
    async def delete(self, key: str) -> None:
        """Удаление ключа из кэша"""
        await self._cache.delete_async(key)
    
    def delete_sync(self, key: str) -> None:
        """Синхронное удаление ключа из кэша"""
        self._cache.delete(key)
    
    async def cleanup_expired(self) -> int:
        """Очистка истекших записей"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._cache.cleanup)
    
    def cleanup_expired_sync(self) -> int:
        """Синхронная очистка истекших записей"""
        return self._cache.cleanup()
    
    async def close(self) -> None:
        """Закрытие кэша"""
        await self._cache.stop_background_cleanup()
    
    def close_sync(self) -> None:
        """Синхронное закрытие кэша"""
        pass  # TTLLRUCache не требует синхронного закрытия