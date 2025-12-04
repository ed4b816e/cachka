import time
import threading
import asyncio
from collections import OrderedDict
from logging import getLogger
from typing import Any, Optional, Callable, Awaitable
from contextlib import contextmanager, asynccontextmanager

logger = getLogger(__name__)


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

        self.maxsize_per_shard = maxsize // shards + 1
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
            self._cache[key] = (value, now)
            self._cache.move_to_end(key)
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