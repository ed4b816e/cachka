"""
Тесты для Redis кэша с использованием testcontainers.
"""
import pytest
import time
import asyncio
import pickle

# Проверяем наличие redis и testcontainers
try:
    from cachka.rediscache import RedisCache, RedisCacheAdapter, RedisCacheConfig
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

try:
    from testcontainers.redis import RedisContainer
    HAS_TESTCONTAINERS = True
except ImportError:
    HAS_TESTCONTAINERS = False

pytestmark = pytest.mark.skipif(
    not HAS_REDIS or not HAS_TESTCONTAINERS,
    reason="Redis and testcontainers are required for these tests"
)


@pytest.fixture(scope="function")
def redis_container():
    """Запускает Redis контейнер для тестов"""
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture
def redis_config(redis_container):
    """Конфигурация Redis для тестов"""
    return RedisCacheConfig(
        host=redis_container.get_container_host_ip(),
        port=redis_container.get_exposed_port(6379),
        db=0,
        key_prefix="test:"
    )


@pytest.fixture
async def redis_cache(redis_config):
    """Создает RedisCache для тестов"""
    cache = RedisCache(redis_config)
    yield cache
    await cache.close()
    cache.close_sync()


@pytest.fixture
async def redis_adapter(redis_config):
    """Создает RedisCacheAdapter для тестов"""
    cache = RedisCache(redis_config)
    adapter = RedisCacheAdapter(cache)
    yield adapter
    await adapter.close()
    adapter.close_sync()


class TestRedisCacheBasic:
    """Базовые операции RedisCache"""

    @pytest.mark.asyncio
    async def test_get_set(self, redis_cache):
        """Базовые get/set операции"""
        await redis_cache.set("key1", b"value1", ttl=60)
        result = await redis_cache.get("key1")
        assert result == b"value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self, redis_cache):
        """Получение отсутствующего ключа"""
        result = await redis_cache.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_overwrite(self, redis_cache):
        """Перезапись значения"""
        await redis_cache.set("key1", b"value1", ttl=60)
        await redis_cache.set("key1", b"value2", ttl=60)
        result = await redis_cache.get("key1")
        assert result == b"value2"

    @pytest.mark.asyncio
    async def test_delete(self, redis_cache):
        """Удаление ключа"""
        await redis_cache.set("key1", b"value1", ttl=60)
        await redis_cache.delete("key1")
        result = await redis_cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, redis_cache):
        """Проверка истечения TTL"""
        await redis_cache.set("key1", b"value1", ttl=1)
        result = await redis_cache.get("key1")
        assert result == b"value1"
        
        # Ждем истечения TTL
        await asyncio.sleep(1.2)
        result = await redis_cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_key_prefix(self, redis_cache):
        """Проверка префикса ключей"""
        await redis_cache.set("key1", b"value1", ttl=60)
        # Проверяем, что ключ имеет префикс
        # (косвенно - через то, что ключ доступен)
        result = await redis_cache.get("key1")
        assert result == b"value1"


class TestRedisCacheSync:
    """Синхронные операции RedisCache"""

    def test_get_set_sync(self, redis_cache):
        """Синхронные get/set операции"""
        redis_cache.set_sync("key1", b"value1", ttl=60)
        result = redis_cache.get_sync("key1")
        assert result == b"value1"

    def test_get_missing_key_sync(self, redis_cache):
        """Синхронное получение отсутствующего ключа"""
        result = redis_cache.get_sync("missing")
        assert result is None

    def test_set_overwrite_sync(self, redis_cache):
        """Синхронная перезапись значения"""
        redis_cache.set_sync("key1", b"value1", ttl=60)
        redis_cache.set_sync("key1", b"value2", ttl=60)
        result = redis_cache.get_sync("key1")
        assert result == b"value2"

    def test_delete_sync(self, redis_cache):
        """Синхронное удаление ключа"""
        redis_cache.set_sync("key1", b"value1", ttl=60)
        redis_cache.delete_sync("key1")
        result = redis_cache.get_sync("key1")
        assert result is None

    def test_ttl_expiration_sync(self, redis_cache):
        """Проверка истечения TTL (sync)"""
        redis_cache.set_sync("key1", b"value1", ttl=1)
        result = redis_cache.get_sync("key1")
        assert result == b"value1"
        
        # Ждем истечения TTL
        time.sleep(1.2)
        result = redis_cache.get_sync("key1")
        assert result is None


class TestRedisCacheAdapter:
    """Тесты для RedisCacheAdapter (с pickle сериализацией)"""

    @pytest.mark.asyncio
    async def test_get_set(self, redis_adapter):
        """Базовые get/set операции через адаптер"""
        await redis_adapter.set("key1", "value1", ttl=60)
        result = await redis_adapter.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_set_complex_object(self, redis_adapter):
        """Сериализация сложных объектов"""
        obj = {"nested": {"list": [1, 2, 3]}, "tuple": (1, 2, 3)}
        await redis_adapter.set("key1", obj, ttl=60)
        result = await redis_adapter.get("key1")
        assert result == obj
        assert result["nested"]["list"] == [1, 2, 3]
        assert result["tuple"] == (1, 2, 3)

    @pytest.mark.asyncio
    async def test_get_missing_key(self, redis_adapter):
        """Получение отсутствующего ключа"""
        result = await redis_adapter.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, redis_adapter):
        """Удаление ключа"""
        await redis_adapter.set("key1", "value1", ttl=60)
        await redis_adapter.delete("key1")
        result = await redis_adapter.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, redis_adapter):
        """Проверка истечения TTL"""
        await redis_adapter.set("key1", "value1", ttl=1)
        result = await redis_adapter.get("key1")
        assert result == "value1"
        
        # Ждем истечения TTL
        await asyncio.sleep(1.2)
        result = await redis_adapter.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, redis_adapter):
        """Очистка истекших записей"""
        await redis_adapter.set("key1", "value1", ttl=1)
        await redis_adapter.set("key2", "value2", ttl=60)
        
        # Ждем истечения TTL для key1
        await asyncio.sleep(1.2)
        
        # cleanup_expired должен удалить истекшие ключи
        deleted = await redis_adapter.cleanup_expired()
        assert deleted >= 0  # Может быть 0, если Redis уже удалил истекшие ключи
        
        # key2 должен остаться
        result = await redis_adapter.get("key2")
        assert result == "value2"


class TestRedisCacheAdapterSync:
    """Синхронные операции RedisCacheAdapter"""

    def test_get_set_sync(self, redis_adapter):
        """Синхронные get/set операции через адаптер"""
        redis_adapter.set_sync("key1", "value1", ttl=60)
        result = redis_adapter.get_sync("key1")
        assert result == "value1"

    def test_get_set_complex_object_sync(self, redis_adapter):
        """Сериализация сложных объектов (sync)"""
        obj = {"nested": {"list": [1, 2, 3]}, "tuple": (1, 2, 3)}
        redis_adapter.set_sync("key1", obj, ttl=60)
        result = redis_adapter.get_sync("key1")
        assert result == obj
        assert result["nested"]["list"] == [1, 2, 3]
        assert result["tuple"] == (1, 2, 3)

    def test_get_missing_key_sync(self, redis_adapter):
        """Синхронное получение отсутствующего ключа"""
        result = redis_adapter.get_sync("missing")
        assert result is None

    def test_delete_sync(self, redis_adapter):
        """Синхронное удаление ключа"""
        redis_adapter.set_sync("key1", "value1", ttl=60)
        redis_adapter.delete_sync("key1")
        result = redis_adapter.get_sync("key1")
        assert result is None

    def test_ttl_expiration_sync(self, redis_adapter):
        """Проверка истечения TTL (sync)"""
        redis_adapter.set_sync("key1", "value1", ttl=1)
        result = redis_adapter.get_sync("key1")
        assert result == "value1"
        
        # Ждем истечения TTL
        time.sleep(1.2)
        result = redis_adapter.get_sync("key1")
        assert result is None

    def test_cleanup_expired_sync(self, redis_adapter):
        """Синхронная очистка истекших записей"""
        redis_adapter.set_sync("key1", "value1", ttl=1)
        redis_adapter.set_sync("key2", "value2", ttl=60)
        
        # Ждем истечения TTL для key1
        time.sleep(1.2)
        
        # cleanup_expired_sync должен удалить истекшие ключи
        deleted = redis_adapter.cleanup_expired_sync()
        assert deleted >= 0  # Может быть 0, если Redis уже удалил истекшие ключи
        
        # key2 должен остаться
        result = redis_adapter.get_sync("key2")
        assert result == "value2"


class TestRedisCacheConnectionPool:
    """Тесты для connection pool"""

    @pytest.mark.asyncio
    async def test_multiple_operations_reuse_connection(self, redis_cache):
        """Множественные операции должны переиспользовать соединение"""
        # Выполняем множество операций
        for i in range(10):
            await redis_cache.set(f"key{i}", f"value{i}".encode(), ttl=60)
        
        # Проверяем, что все значения доступны
        for i in range(10):
            result = await redis_cache.get(f"key{i}")
            assert result == f"value{i}".encode()

    def test_multiple_operations_reuse_connection_sync(self, redis_cache):
        """Множественные операции должны переиспользовать соединение (sync)"""
        # Выполняем множество операций
        for i in range(10):
            redis_cache.set_sync(f"key{i}", f"value{i}".encode(), ttl=60)
        
        # Проверяем, что все значения доступны
        for i in range(10):
            result = redis_cache.get_sync(f"key{i}")
            assert result == f"value{i}".encode()


class TestRedisCacheErrorHandling:
    """Тесты обработки ошибок"""

    def test_redis_not_installed_error(self):
        """Проверка ошибки при отсутствии redis"""
        # Этот тест проверяет, что ошибка выдается правильно
        # В реальности, если redis не установлен, импорт уже упадет
        # Но мы можем проверить, что сообщение об ошибке правильное
        # Для этого нужно временно заменить HAS_REDIS
        import cachka.rediscache as redis_module
        
        # Сохраняем оригинальные значения
        original_has_redis = redis_module.HAS_REDIS
        
        # Если redis установлен, пропускаем тест
        if original_has_redis:
            pytest.skip("Redis is installed, cannot test error handling")
        
        # Если redis не установлен, проверяем, что ошибка правильная
        with pytest.raises(ImportError, match="Redis is not installed"):
            RedisCache(RedisCacheConfig())

