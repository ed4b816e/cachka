import asyncio
from contextlib import asynccontextmanager

import aiosqlite
import pickle
import time
import os
import threading
import secrets
from typing import Any, Optional, Dict
from abc import ABC, abstractmethod

from cachka.ttllrucache import TTLLRUCache

# === Optional deps ===
try:
    from prometheus_client import generate_latest
except ImportError:
    def generate_latest():
        return b"# Prometheus not available\n"

try:
    from opentelemetry import trace
    from opentelemetry.trace import SpanKind
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False
    class DummyTracer:
        def start_as_current_span(self, *a, **kw): return self
        def __enter__(self): return self
        def __exit__(self, *a): pass
    trace = type('trace', (), {'get_tracer': lambda *a: DummyTracer()})

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

import structlog
logger = structlog.get_logger(__name__)

# === Config ===
from pydantic import BaseModel

class CacheConfig(BaseModel):
    db_path: str = "cache.db"
    name: str = "default"
    l1_maxsize: int = 1024
    l1_ttl: int = 300
    vacuum_interval: Optional[int] = 3600
    cleanup_on_start: bool = True
    enable_metrics: bool = False
    enable_encryption: bool = False
    encryption_key: Optional[str] = None  # base64-encoded 32-byte key
    max_key_length: int = 512
    circuit_breaker_threshold: int = 50
    circuit_breaker_window: int = 60


# === Storage Backend ===
class StorageBackend(ABC):
    @abstractmethod
    async def get(self, key: str) -> Optional[bytes]: ...
    @abstractmethod
    async def set(self, key: str, value: bytes, ttl: int) -> None: ...
    @abstractmethod
    async def cleanup_expired(self) -> int: ...
    @abstractmethod
    async def close(self) -> None: ...


class SQLiteStorage(StorageBackend):
    def __init__(self, db_path: str, config: CacheConfig):
        self.db_path = db_path
        self.config = config
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()
        self._encryption_key = None

        if config.enable_encryption and config.encryption_key:
            if not HAS_CRYPTO:
                raise RuntimeError("Install 'cryptography' for encryption")
            import base64
            raw_key = base64.b64decode(config.encryption_key)
            if len(raw_key) != 32:
                raise ValueError("Encryption key must be 32 bytes (base64-encoded)")
            self._encryption_key = raw_key

    @staticmethod
    async def _init_db(conn: aiosqlite.Connection):
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA cache_size=-10000")
        await conn.execute("PRAGMA temp_store=MEMORY")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL,
                expires_at REAL NOT NULL
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)")

    @asynccontextmanager
    async def _get_connection(self):
        async with self._lock:
            if self._connection is None:
                self._connection = await aiosqlite.connect(
                    self.db_path,
                    detect_types=0,
                    isolation_level=None,
                    timeout=30.0,
                )
                await self._init_db(self._connection)
            yield self._connection

    def _encrypt(self, data: bytes) -> bytes:
        if not self._encryption_key:
            return data
        aesgcm = AESGCM(self._encryption_key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, data, None)
        return nonce + ct

    def _decrypt(self, data: bytes) -> bytes:
        if not self._encryption_key:
            return data
        if len(data) < 12:
            raise ValueError("Invalid encrypted data")
        nonce, ct = data[:12], data[12:]
        aesgcm = AESGCM(self._encryption_key)
        return aesgcm.decrypt(nonce, ct, None)

    async def get(self, key: str) -> Optional[bytes]:
        now = time.time()
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT value FROM cache WHERE key = ? AND expires_at > ?", (key, now)
            )
            row = await cursor.fetchone()
            if row and row[0] is not None:
                return self._decrypt(row[0])
            return None

    async def set(self, key: str, value: bytes, ttl: int):
        expires_at = time.time() + ttl
        encrypted = self._encrypt(value)
        async with self._get_connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, encrypted, expires_at)
            )
            await conn.commit()

    async def cleanup_expired(self) -> int:
        now = time.time()
        async with self._get_connection() as conn:
            cursor = await conn.execute("DELETE FROM cache WHERE expires_at <= ?", (now,))
            await conn.commit()
            return cursor.rowcount

    async def close(self):
        if self._connection:
            await self._connection.close()
            self._connection = None


# === Circuit Breaker ===
class CircuitBreaker:
    def __init__(self, failure_threshold: int, recovery_timeout: int):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"
        self._lock = threading.Lock()

    def call_failed(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"

    def call_succeeded(self):
        with self._lock:
            self.failure_count = 0
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"

    def can_execute(self) -> bool:
        with self._lock:
            if self.state == "CLOSED":
                return True
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    return True
                return False
            return True


# === Main Cache ===
class AsyncCache:
    def __init__(self, config: CacheConfig):
        self.config = config
        self.storage = SQLiteStorage(config.db_path, config)
        self._l1_cache = TTLLRUCache(maxsize=config.l1_maxsize, ttl=config.l1_ttl)
        self._l1_lock = threading.RLock()
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_threshold,
            recovery_timeout=config.circuit_breaker_window
        )
        self._tracer = trace.get_tracer(__name__)
        self._shutdown_event = asyncio.Event()
        self._gc_task: Optional[asyncio.Task] = None

        # Metrics
        self._metrics = None
        if config.enable_metrics:
            self._init_metrics(config.name)

        if config.vacuum_interval:
            self._gc_task = asyncio.create_task(self._maintenance_loop())

    @property
    def l1_cache(self) -> TTLLRUCache:
        return self._l1_cache

    @property
    def l1_lock(self) -> threading.RLock:
        return self._l1_lock

    def _init_metrics(self, cache_name: str):
        try:
            from prometheus_client import Counter, Histogram
            self._metrics = {
                "requests": Counter("cache_requests_total", "Cache requests", ["cache", "type"]),
                "duration": Histogram("cache_operation_duration_seconds", "Operation duration", ["cache", "operation"]),
                "errors": Counter("cache_errors_total", "Cache errors", ["cache", "error_type"]),
            }
        except ImportError:
            self._metrics = None

    async def _maintenance_loop(self):
        while not self._shutdown_event.is_set():
            # Спим по частям, чтобы быстро реагировать на shutdown
            slept = 0
            interval = self.config.vacuum_interval
            while slept < interval and not self._shutdown_event.is_set():
                sleep_step = min(1.0, interval - slept)  # проверяем каждую секунду
                await asyncio.sleep(sleep_step)
                slept += sleep_step

            if not self._shutdown_event.is_set():
                await self.storage.cleanup_expired()

    async def get(self, key: str) -> Optional[Any]:
        if not self._circuit_breaker.can_execute():
            logger.warning("circuit_breaker_open", key=key)
            if self._metrics:
                self._metrics["errors"].labels(error_type="circuit_breaker").inc()
            return None

        with self._tracer.start_as_current_span("cache.get", kind=SpanKind.CLIENT) as span:
            span.set_attribute("cache.key", key)
            start = time.perf_counter()

            try:
                with self._l1_lock:
                    if key in self._l1_cache:
                        span.set_attribute("cache.hit", "l1")
                        if self._metrics:
                            self._metrics["requests"].labels(type="l1_hit").inc()
                        return self._l1_cache[key]

                raw = await self.storage.get(key)
                if raw is None:
                    span.set_attribute("cache.hit", "miss")
                    if self._metrics:
                        self._metrics["requests"].labels(type="miss").inc()
                    return None

                value = pickle.loads(raw)
                with self._l1_lock:
                    self._l1_cache[key] = value
                span.set_attribute("cache.hit", "l2")
                if self._metrics:
                    self._metrics["requests"].labels(type="l2_hit").inc()
                self._circuit_breaker.call_succeeded()
                return value

            except Exception as e:
                self._circuit_breaker.call_failed()
                error_type = type(e).__name__
                logger.error("cache_get_error", key=key, error=error_type)
                if self._metrics:
                    self._metrics["errors"].labels(error_type=error_type).inc()
                span.record_exception(e)
                return None
            finally:
                if self._metrics:
                    self._metrics["duration"].labels(operation="get").observe(time.perf_counter() - start)

    async def set(self, key: str, value: Any, ttl: int):
        if not self._circuit_breaker.can_execute():
            return

        with self._tracer.start_as_current_span("cache.set", kind=SpanKind.CLIENT) as span:
            span.set_attribute("cache.key", key)
            start = time.perf_counter()

            try:
                pickled = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
                await self.storage.set(key, pickled, ttl)

                with self._l1_lock:
                    self._l1_cache[key] = value

                self._circuit_breaker.call_succeeded()
            except Exception as e:
                self._circuit_breaker.call_failed()
                error_type = type(e).__name__
                logger.error("cache_set_error", key=key, error=error_type)
                if self._metrics:
                    self._metrics["errors"].labels(error_type=error_type).inc()
                span.record_exception(e)
            finally:
                if self._metrics:
                    self._metrics["duration"].labels(operation="set").observe(time.perf_counter() - start)

    async def health_check(self) -> Dict[str, Any]:
        try:
            test_key = "health_" + secrets.token_hex(8)
            await self.set(test_key, "ok", 10)
            val = await self.get(test_key)
            healthy = (val == "ok")
        except Exception as e:
            healthy = False
            logger.error("health_check_failed", error=str(e))

        return {
            "status": "healthy" if healthy else "unhealthy",
            "l1_size": len(self._l1_cache),
            "circuit_breaker": self._circuit_breaker.state,
            "storage": "ok" if healthy else "failed"
        }

    async def graceful_shutdown(self):
        self._shutdown_event.set()
        if self._gc_task:
            try:
                await asyncio.wait_for(self._gc_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("gc_task_timeout")
        await self.storage.close()

    def get_metrics_text(self) -> str:
        return generate_latest().decode('utf-8')
