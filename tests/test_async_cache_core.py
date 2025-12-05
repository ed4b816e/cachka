import pytest
import time
import asyncio
from cachka.core import AsyncCache, CacheConfig, CircuitBreaker
from cachka.ttllrucache import MemoryCacheConfig
from cachka.sqlitecache import SQLiteCacheConfig, SQLiteStorage


class TestAsyncCacheL1L2:
    """Тесты взаимодействия L1 и L2 кэша"""

    @pytest.fixture
    def config(self):
        return CacheConfig(
            cache_layers=[
                ("memory", MemoryCacheConfig(maxsize=10, ttl=60)),
                ("sqlite", SQLiteCacheConfig(db_path=":memory:"))
            ],
            vacuum_interval=None,
            cleanup_on_start=False
        )

    @pytest.fixture
    async def cache(self, config):
        cache = AsyncCache(config)
        yield cache
        await cache.graceful_shutdown()

    @pytest.mark.asyncio
    async def test_l1_hit(self, cache):
        """Попадание в L1 кэш"""
        await cache.set("key1", "value1", ttl=60)
        # Первый get загрузит в L1
        result1 = await cache.get("key1")
        assert result1 == "value1"
        
        # Второй get должен быть из L1
        result2 = await cache.get("key1")
        assert result2 == "value1"

    @pytest.mark.asyncio
    async def test_l1_miss_l2_miss(self, cache):
        """Промах обоих уровней"""
        result = await cache.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_overwrite(self, cache):
        """Перезапись существующего значения"""
        await cache.set("key1", "value1", ttl=60)
        await cache.set("key1", "value2", ttl=60)
        assert await cache.get("key1") == "value2"


class TestAsyncCacheCircuitBreaker:
    """Тесты Circuit Breaker"""

    @pytest.fixture
    def config(self):
        return CacheConfig(
            cache_layers=[
                "memory",
                ("sqlite", SQLiteCacheConfig(db_path=":memory:"))
            ],
            circuit_breaker_threshold=3,
            circuit_breaker_window=1,
            vacuum_interval=None,
            cleanup_on_start=False
        )

    @pytest.fixture
    async def cache(self, config):
        cache = AsyncCache(config)
        yield cache
        await cache.graceful_shutdown()

    @pytest.mark.asyncio
    async def test_circuit_breaker_closed(self, cache):
        """Нормальная работа (CLOSED)"""
        assert cache._circuit_breaker.state == "CLOSED"
        await cache.set("key1", "value1", ttl=60)
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self, cache):
        """Открытие при ошибках"""
        # Создаем ситуацию с ошибками (например, поврежденные данные)
        # Для этого нужно замокать storage или использовать реальную ошибку
        breaker = cache._circuit_breaker
        
        # Симулируем ошибки
        for _ in range(3):
            breaker.call_failed()
        
        assert breaker.state == "OPEN"

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_requests(self, cache):
        """Блокировка запросов в OPEN"""
        breaker = cache._circuit_breaker
        breaker.state = "OPEN"
        breaker.last_failure_time = time.time()
        
        # Get должен вернуть None из-за circuit breaker
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self, cache):
        """Восстановление после таймаута"""
        breaker = cache._circuit_breaker
        breaker.state = "OPEN"
        breaker.last_failure_time = time.time() - 2  # 2 секунды назад
        
        # Должен перейти в HALF_OPEN
        assert breaker.can_execute() is True
        assert breaker.state == "HALF_OPEN"

    @pytest.mark.asyncio
    async def test_circuit_breaker_resets_on_success(self, cache):
        """Сброс при успехе"""
        breaker = cache._circuit_breaker
        breaker.state = "HALF_OPEN"
        
        # Успешный вызов должен закрыть circuit breaker
        breaker.call_succeeded()
        assert breaker.state == "CLOSED"
        assert breaker.failure_count == 0


class TestAsyncCacheMaintenance:
    """Тесты maintenance loop"""

    @pytest.fixture
    def config(self):
        return CacheConfig(
            cache_layers=[
                "memory",
                ("sqlite", SQLiteCacheConfig(db_path=":memory:"))
            ],
            vacuum_interval=1,  # 1 second
            cleanup_on_start=False
        )

    @pytest.fixture
    async def cache(self, config):
        cache = AsyncCache(config)
        yield cache
        await cache.graceful_shutdown()

    @pytest.mark.asyncio
    async def test_maintenance_loop_runs(self, cache):
        """Цикл очистки работает"""
        assert cache._gc_task is not None
        assert not cache._gc_task.done()

    @pytest.mark.asyncio
    async def test_maintenance_loop_stops_on_shutdown(self, cache):
        """Остановка при shutdown"""
        await cache.graceful_shutdown()
        # Task должен быть завершен или отменен
        assert cache._gc_task is None or cache._gc_task.done()

    @pytest.mark.asyncio
    async def test_no_maintenance_loop_when_disabled(self):
        """Нет цикла при vacuum_interval=None"""
        config = CacheConfig(
            cache_layers=[
                "memory",
                ("sqlite", SQLiteCacheConfig(db_path=":memory:"))
            ],
            vacuum_interval=None,
            cleanup_on_start=False
        )
        cache = AsyncCache(config)
        assert cache._gc_task is None
        await cache.graceful_shutdown()


class TestAsyncCacheHealthCheck:
    """Тесты health check"""

    @pytest.fixture
    def config(self):
        return CacheConfig(
            vacuum_interval=None,
            cleanup_on_start=False
        )

    @pytest.fixture
    async def cache(self, config):
        cache = AsyncCache(config)
        yield cache
        await cache.graceful_shutdown()

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, cache):
        """Здоровый кэш"""
        health = await cache.health_check()
        assert health["status"] == "healthy"
        assert "circuit_breaker" in health

    @pytest.mark.asyncio
    async def test_health_check_includes_metrics(self, cache):
        """Метрики в health check"""
        health = await cache.health_check()
        assert health["circuit_breaker"] in ["CLOSED", "OPEN", "HALF_OPEN"]


class TestAsyncCacheEdgeCases:
    """Edge cases"""

    @pytest.fixture
    def config(self):
        return CacheConfig(
            vacuum_interval=None,
            cleanup_on_start=False
        )

    @pytest.fixture
    async def cache(self, config):
        cache = AsyncCache(config)
        yield cache
        await cache.graceful_shutdown()

    @pytest.mark.asyncio
    async def test_none_value(self, cache):
        """Кэширование None"""
        await cache.set("key1", None, ttl=60)
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_complex_objects(self, cache):
        """Сложные объекты"""
        obj = {
            "nested": {
                "list": [1, 2, 3],
                "dict": {"a": 1, "b": 2}
            }
        }
        await cache.set("key1", obj, ttl=60)
        result = await cache.get("key1")
        assert result == obj
        assert result["nested"]["list"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, cache):
        """Корректное завершение"""
        from cachka.sqlitecache import SQLiteStorageAdapter
        
        await cache.set("key1", "value1", ttl=60)
        await cache.graceful_shutdown()
        # После shutdown storage должен быть закрыт
        # Проверяем через адаптеры, так как _caches содержит адаптеры, а не сами storage
        sqlite_closed = False
        for layer in cache._caches:
            if isinstance(layer, SQLiteStorageAdapter):
                sqlite_closed = (layer._storage._connection is None)
                break
        assert sqlite_closed

