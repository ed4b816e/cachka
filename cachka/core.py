import asyncio
import dataclasses
import secrets
import threading
import time
from typing import (
    Any,
    Optional,
    Union,
)

from cachka.interface import ICache
from cachka.sqlitecache import (
    SQLiteCacheConfig,
    SQLiteStorage,
    SQLiteStorageAdapter,
)
from cachka.ttllrucache import (
    MemoryCacheConfig,
    TTLLRUCache,
    TTLLRUCacheAdapter,
)

# Redis - опциональная зависимость
try:
    from cachka.rediscache import (
        RedisCache,
        RedisCacheAdapter,
        RedisCacheConfig,
    )

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    RedisCache = None
    RedisCacheAdapter = None
    RedisCacheConfig = None

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
        def start_as_current_span(self, *a, **kw):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    trace = type("trace", (), {"get_tracer": lambda *a: DummyTracer()})


import structlog

logger = structlog.get_logger(__name__)

# === Config ===


@dataclasses.dataclass
class CacheConfig:
    """Основная конфигурация кэша"""

    name: str = "default"
    vacuum_interval: Optional[int] = 3600
    cleanup_on_start: bool = True
    enable_metrics: bool = False
    circuit_breaker_threshold: int = 50
    circuit_breaker_window: int = 60

    # Список кэшей: строка (название с дефолтными параметрами) или кортеж (название, конфиг)
    # Например: ["memory", "sqlite"] или [("memory", MemoryCacheConfig(maxsize=2048)), "sqlite"]
    cache_layers: list[Union[str, tuple[str, Any]]] = None


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


# === Cache Factory ===
def _create_cache_layer(layer_type: str, layer_config: Optional[Any]) -> ICache:
    """
    Фабрика для создания кэшей по типу.

    Args:
        layer_type: Тип кэша ("memory", "sqlite", и т.д.)
        layer_config: Конфигурация конкретного кэша (если None, используются дефолтные значения)

    Returns:
        Экземпляр ICache
    """
    if layer_type == "memory":
        if layer_config is None:
            memory_config = MemoryCacheConfig()
        elif isinstance(layer_config, MemoryCacheConfig):
            memory_config = layer_config
        else:
            raise ValueError(
                f"Invalid config for memory cache: expected MemoryCacheConfig, got {type(layer_config)}"
            )

        ttl_cache = TTLLRUCache(
            maxsize=memory_config.maxsize,
            ttl=memory_config.ttl,
            shards=memory_config.shards,
            enable_metrics=memory_config.enable_metrics,
            name=memory_config.name,
        )
        return TTLLRUCacheAdapter(ttl_cache)

    elif layer_type == "sqlite":
        if layer_config is None:
            sqlite_config = SQLiteCacheConfig()
        elif isinstance(layer_config, SQLiteCacheConfig):
            sqlite_config = layer_config
        else:
            raise ValueError(
                f"Invalid config for sqlite cache: expected SQLiteCacheConfig, got {type(layer_config)}"
            )

        storage_backend = SQLiteStorage(sqlite_config.db_path, sqlite_config)
        return SQLiteStorageAdapter(storage_backend)

    elif layer_type == "redis":
        if not HAS_REDIS:
            raise ImportError(
                "Redis is not installed. To use Redis cache, install it with:\n"
                "  pip install redis\n"
                "or\n"
                "  pip install cachka[redis]"
            )
        if layer_config is None:
            redis_config = RedisCacheConfig()
        elif isinstance(layer_config, RedisCacheConfig):
            redis_config = layer_config
        else:
            raise ValueError(
                f"Invalid config for redis cache: expected RedisCacheConfig, got {type(layer_config)}"
            )

        redis_cache = RedisCache(redis_config)
        return RedisCacheAdapter(redis_cache)

    else:
        raise ValueError(
            f"Unknown cache layer type: {layer_type}. Supported types: 'memory', 'sqlite', 'redis'"
        )


# === Main Cache ===
class AsyncCache(ICache):
    def __init__(self, config: CacheConfig):
        self.config = config

        if not config.cache_layers:
            config.cache_layers = ["memory", "sqlite"]

        # Создаем кэши в порядке, указанном в конфиге
        self._caches: list[ICache] = []
        self._cache_configs: list[Optional[Any]] = []

        for layer_spec in config.cache_layers:
            # Парсим спецификацию слоя: строка или кортеж (название, конфиг)
            if isinstance(layer_spec, str):
                layer_type = layer_spec
                layer_config = None
            elif isinstance(layer_spec, tuple) and len(layer_spec) == 2:
                layer_type, layer_config = layer_spec
            else:
                raise ValueError(
                    f"Invalid cache layer specification: {layer_spec}. "
                    f"Expected str or tuple[str, Any], got {type(layer_spec)}"
                )

            cache = _create_cache_layer(layer_type, layer_config)
            self._caches.append(cache)
            self._cache_configs.append(layer_config)

        self._circuit_breaker = CircuitBreaker(
            failure_threshold=config.circuit_breaker_threshold,
            recovery_timeout=config.circuit_breaker_window,
        )
        self._tracer = trace.get_tracer(__name__)
        self._shutdown_event = asyncio.Event()
        self._gc_task: Optional[asyncio.Task] = None

        # Metrics
        if config.enable_metrics:
            self._init_metrics(config.name)
        else:
            self._metrics = None

        if config.vacuum_interval:
            self._gc_task = asyncio.create_task(self._maintenance_loop())

    def _init_metrics(self, cache_name: str):
        from prometheus_client import (
            Counter,
            Histogram,
        )

        self._metrics = {
            "requests": Counter(
                "cache_requests_total", "Cache requests", ["cache", "type"]
            ),
            "duration": Histogram(
                "cache_operation_duration_seconds",
                "Operation duration",
                ["cache", "operation"],
            ),
            "errors": Counter(
                "cache_errors_total", "Cache errors", ["cache", "error_type"]
            ),
        }

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
                # Очищаем все кэши, которые поддерживают cleanup_expired
                for cache in self._caches:
                    try:
                        await cache.cleanup_expired()
                    except NotImplementedError:
                        pass  # Кэш не поддерживает cleanup_expired

    async def get(self, key: str) -> Optional[Any]:
        if not self._circuit_breaker.can_execute():
            logger.warning("circuit_breaker_open", key=key)
            if self._metrics:
                self._metrics["errors"].labels(
                    cache=self.config.name, error_type="circuit_breaker"
                ).inc()
            return None

        with self._tracer.start_as_current_span(
            "cache.get", kind=SpanKind.CLIENT
        ) as span:
            span.set_attribute("cache.key", key)
            start = time.perf_counter()

            try:
                # Проходим по кэшам в порядке их указания в конфиге
                for i, cache in enumerate(self._caches):
                    value = await cache.get(key)
                    if value is not None:
                        # Найдено в кэше на уровне i
                        layer_name = f"layer_{i}"
                        span.set_attribute("cache.hit", layer_name)
                        if self._metrics:
                            self._metrics["requests"].labels(
                                cache=self.config.name, type=f"hit_layer_{i}"
                            ).inc()

                        # Промотируем в предыдущие кэши
                        for j in range(i):
                            try:
                                promo_ttl = self._get_cache_ttl(j)
                                await self._caches[j].set(key, value, promo_ttl)
                            except Exception:
                                pass  # Игнорируем ошибки при промоции

                        self._circuit_breaker.call_succeeded()
                        return value

                # Не найдено ни в одном кэше
                span.set_attribute("cache.hit", "miss")
                if self._metrics:
                    self._metrics["requests"].labels(
                        cache=self.config.name, type="miss"
                    ).inc()
                self._circuit_breaker.call_succeeded()
                return None

            except Exception as e:
                self._circuit_breaker.call_failed()
                error_type = type(e).__name__
                logger.error("cache_get_error", key=key, error=error_type)
                if self._metrics:
                    self._metrics["errors"].labels(
                        cache=self.config.name, error_type=error_type
                    ).inc()
                span.record_exception(e)
                return None
            finally:
                if self._metrics:
                    self._metrics["duration"].labels(
                        cache=self.config.name, operation="get"
                    ).observe(time.perf_counter() - start)

    def _get_cache_ttl(self, cache_index: int, default_ttl: int = 300) -> int:
        """Получает TTL для кэша по индексу из его конфига"""
        cache_config = self._cache_configs[cache_index]
        if cache_config is not None and isinstance(cache_config, MemoryCacheConfig):
            return cache_config.ttl
        return default_ttl

    async def set(self, key: str, value: Any, ttl: int):
        if not self._circuit_breaker.can_execute():
            return

        with self._tracer.start_as_current_span(
            "cache.set", kind=SpanKind.CLIENT
        ) as span:
            span.set_attribute("cache.key", key)
            start = time.perf_counter()

            try:
                # Сохраняем во все кэши (write-through)
                for i, cache in enumerate(self._caches):
                    try:
                        cache_ttl = self._get_cache_ttl(i, ttl)
                        await cache.set(key, value, cache_ttl)
                    except Exception as e:
                        logger.warning("cache_set_layer_error", layer=i, error=str(e))

                self._circuit_breaker.call_succeeded()
            except Exception as e:
                self._circuit_breaker.call_failed()
                error_type = type(e).__name__
                logger.error("cache_set_error", key=key, error=error_type)
                if self._metrics:
                    self._metrics["errors"].labels(
                        cache=self.config.name, error_type=error_type
                    ).inc()
                span.record_exception(e)
            finally:
                if self._metrics:
                    self._metrics["duration"].labels(
                        cache=self.config.name, operation="set"
                    ).observe(time.perf_counter() - start)

    # === Синхронные методы (нативная реализация) ===

    def get_sync(self, key: str) -> Optional[Any]:
        """Синхронное получение значения из кэша"""
        if not self._circuit_breaker.can_execute():
            logger.warning("circuit_breaker_open", key=key)
            if self._metrics:
                self._metrics["errors"].labels(
                    cache=self.config.name, error_type="circuit_breaker"
                ).inc()
            return None

        start = time.perf_counter()

        try:
            # Проходим по кэшам в порядке их указания в конфиге
            for i, cache in enumerate(self._caches):
                value = cache.get_sync(key)
                if value is not None:
                    # Найдено в кэше на уровне i
                    if self._metrics:
                        self._metrics["requests"].labels(
                            cache=self.config.name, type=f"hit_layer_{i}"
                        ).inc()

                    # Промотируем в предыдущие кэши
                    for j in range(i):
                        try:
                            promo_ttl = self._get_cache_ttl(j)
                            self._caches[j].set_sync(key, value, promo_ttl)
                        except Exception:
                            pass  # Игнорируем ошибки при промоции

                    self._circuit_breaker.call_succeeded()
                    return value

            # Не найдено ни в одном кэше
            if self._metrics:
                self._metrics["requests"].labels(
                    cache=self.config.name, type="miss"
                ).inc()
            self._circuit_breaker.call_succeeded()
            return None

        except Exception as e:
            self._circuit_breaker.call_failed()
            error_type = type(e).__name__
            logger.error("cache_get_error", key=key, error=error_type)
            if self._metrics:
                self._metrics["errors"].labels(
                    cache=self.config.name, error_type=error_type
                ).inc()
            return None
        finally:
            if self._metrics:
                self._metrics["duration"].labels(
                    cache=self.config.name, operation="get"
                ).observe(time.perf_counter() - start)

    def set_sync(self, key: str, value: Any, ttl: int) -> None:
        """Синхронная установка значения в кэш"""
        if not self._circuit_breaker.can_execute():
            return

        start = time.perf_counter()

        try:
            # Сохраняем во все кэши (write-through)
            for i, cache in enumerate(self._caches):
                try:
                    cache_ttl = self._get_cache_ttl(i, ttl)
                    cache.set_sync(key, value, cache_ttl)
                except Exception as e:
                    logger.warning("cache_set_layer_error", layer=i, error=str(e))

            self._circuit_breaker.call_succeeded()
        except Exception as e:
            self._circuit_breaker.call_failed()
            error_type = type(e).__name__
            logger.error("cache_set_error", key=key, error=error_type)
            if self._metrics:
                self._metrics["errors"].labels(
                    cache=self.config.name, error_type=error_type
                ).inc()
        finally:
            if self._metrics:
                self._metrics["duration"].labels(
                    cache=self.config.name, operation="set"
                ).observe(time.perf_counter() - start)

    async def health_check(self) -> dict[str, Any]:
        try:
            test_key = "health_" + secrets.token_hex(8)
            await self.set(test_key, "ok", 10)
            val = await self.get(test_key)
            healthy = val == "ok"
        except Exception as e:
            healthy = False
            logger.error("health_check_failed", error=str(e))

        return {
            "status": "healthy" if healthy else "unhealthy",
            "circuit_breaker": self._circuit_breaker.state,
            "cache_layers_count": len(self._caches),
        }

    async def graceful_shutdown(self):
        self._shutdown_event.set()
        if self._gc_task:
            try:
                await asyncio.wait_for(self._gc_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("gc_task_timeout")

        # Закрываем все кэши
        for cache in self._caches:
            try:
                await cache.close()
            except Exception as e:
                logger.warning("cache_close_error", error=str(e))

    def get_metrics_text(self) -> str:
        return generate_latest().decode("utf-8")

    async def cleanup_expired(self) -> None:
        for cache in self._caches:
            await cache.cleanup_expired()

    async def cleanup(self) -> None:
        await self.cleanup_expired()
