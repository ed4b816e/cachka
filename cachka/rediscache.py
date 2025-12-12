"""
Redis кэш: реализация, конфигурация и адаптер.
"""
import dataclasses
import pickle
from typing import Any, Optional

from typing_extensions import Protocol

from cachka.interface import ICache

# === Optional deps ===
try:
    import redis
    import redis.asyncio as aioredis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    class redis(Protocol):
        __slots__ = ["Redis"]
    class aioredis(Protocol):
        __slots__ = ["Redis"]


# === Config ===

@dataclasses.dataclass
class RedisCacheConfig:
    """Конфигурация для Redis кэша"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    socket_timeout: Optional[float] = None
    socket_connect_timeout: Optional[float] = None
    max_connections: int = 50
    decode_responses: bool = False  # Должно быть False для работы с bytes
    key_prefix: str = "cachka:"  # Префикс для всех ключей


# === Implementation ===

class RedisCache:
    """Реализация Redis кэша с поддержкой async и sync API"""
    
    def __init__(self, config: RedisCacheConfig):
        if not HAS_REDIS:
            raise ImportError(
                "Redis is not installed. To use Redis cache, install it with:\n"
                "  pip install redis\n"
                "or\n"
                "  pip install cachka[redis]"
            )
        
        self.config = config
        self._async_client: Optional[aioredis.Redis] = None
        self._sync_client: Optional[redis.Redis] = None
        self._async_pool: Optional[aioredis.ConnectionPool] = None
        self._sync_pool: Optional[redis.ConnectionPool] = None
    
    def _get_async_client(self) -> aioredis.Redis:
        """Получить или создать async Redis клиент"""
        if self._async_client is None:
            if self._async_pool is None:
                self._async_pool = aioredis.ConnectionPool(
                    host=self.config.host,
                    port=self.config.port,
                    db=self.config.db,
                    password=self.config.password,
                    socket_timeout=self.config.socket_timeout,
                    socket_connect_timeout=self.config.socket_connect_timeout,
                    max_connections=self.config.max_connections,
                    decode_responses=False,  # Всегда False для работы с bytes
                )
            self._async_client = aioredis.Redis(connection_pool=self._async_pool)
        return self._async_client
    
    def _get_sync_client(self) -> redis.Redis:
        """Получить или создать sync Redis клиент"""
        if self._sync_client is None:
            if self._sync_pool is None:
                self._sync_pool = redis.ConnectionPool(
                    host=self.config.host,
                    port=self.config.port,
                    db=self.config.db,
                    password=self.config.password,
                    socket_timeout=self.config.socket_timeout,
                    socket_connect_timeout=self.config.socket_connect_timeout,
                    max_connections=self.config.max_connections,
                    decode_responses=False,  # Всегда False для работы с bytes
                )
            self._sync_client = redis.Redis(connection_pool=self._sync_pool)
        return self._sync_client
    
    def _make_key(self, key: str) -> str:
        """Добавить префикс к ключу"""
        return f"{self.config.key_prefix}{key}"
    
    # === Async methods ===
    
    async def get(self, key: str) -> Optional[bytes]:
        """Асинхронное получение значения из Redis"""
        client = self._get_async_client()
        prefixed_key = self._make_key(key)
        return await client.get(prefixed_key)
    
    async def set(self, key: str, value: bytes, ttl: int) -> None:
        """Асинхронная установка значения в Redis с TTL"""
        client = self._get_async_client()
        prefixed_key = self._make_key(key)
        await client.setex(prefixed_key, ttl, value)
    
    async def delete(self, key: str) -> None:
        """Асинхронное удаление ключа из Redis"""
        client = self._get_async_client()
        prefixed_key = self._make_key(key)
        await client.delete(prefixed_key)
    
    async def cleanup_expired(self) -> int:
        """
        Очистка истекших записей.
        
        В Redis истечение записей происходит автоматически,
        но можно принудительно удалить все ключи с префиксом.
        Возвращает количество удаленных ключей.
        """
        client = self._get_async_client()
        # Паттерн для поиска всех ключей с префиксом
        pattern = f"{self.config.key_prefix}*"
        # Используем SCAN для безопасного удаления ключей
        deleted = 0
        async for key in client.scan_iter(match=pattern):
            await client.delete(key)
            deleted += 1
        return deleted
    
    async def close(self) -> None:
        """Закрытие async соединений"""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None
        if self._async_pool:
            await self._async_pool.aclose()
            self._async_pool = None
    
    # === Sync methods ===
    
    def get_sync(self, key: str) -> Optional[bytes]:
        """Синхронное получение значения из Redis"""
        client = self._get_sync_client()
        prefixed_key = self._make_key(key)
        return client.get(prefixed_key)
    
    def set_sync(self, key: str, value: bytes, ttl: int) -> None:
        """Синхронная установка значения в Redis с TTL"""
        client = self._get_sync_client()
        prefixed_key = self._make_key(key)
        client.setex(prefixed_key, ttl, value)
    
    def delete_sync(self, key: str) -> None:
        """Синхронное удаление ключа из Redis"""
        client = self._get_sync_client()
        prefixed_key = self._make_key(key)
        client.delete(prefixed_key)
    
    def cleanup_expired_sync(self) -> int:
        """
        Синхронная очистка истекших записей.
        
        В Redis истечение записей происходит автоматически,
        но можно принудительно удалить все ключи с префиксом.
        Возвращает количество удаленных ключей.
        """
        client = self._get_sync_client()
        # Паттерн для поиска всех ключей с префиксом
        pattern = f"{self.config.key_prefix}*"
        # Используем SCAN для безопасного удаления ключей
        deleted = 0
        for key in client.scan_iter(match=pattern):
            client.delete(key)
            deleted += 1
        return deleted
    
    def close_sync(self) -> None:
        """Закрытие sync соединений"""
        if self._sync_client:
            self._sync_client.close()
            self._sync_client = None
        if self._sync_pool:
            self._sync_pool.disconnect()
            self._sync_pool = None


# === Adapter ===

class RedisCacheAdapter(ICache):
    """
    Адаптер для RedisCache, реализующий интерфейс ICache.
    
    RedisCache работает с bytes (сериализованными данными),
    этот адаптер добавляет pickle сериализацию/десериализацию.
    """
    
    def __init__(self, cache: RedisCache):
        if not HAS_REDIS:
            raise ImportError(
                "Redis is not installed. To use Redis cache, install it with:\n"
                "  pip install redis\n"
                "or\n"
                "  pip install cachka[redis]"
            )
        self._cache = cache
    
    async def get(self, key: str) -> Optional[Any]:
        """Асинхронное получение значения из кэша"""
        raw = await self._cache.get(key)
        if raw is None:
            return None
        return pickle.loads(raw)
    
    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Асинхронная установка значения в кэш"""
        pickled = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        await self._cache.set(key, pickled, ttl)
    
    def get_sync(self, key: str) -> Optional[Any]:
        """Синхронное получение значения из кэша"""
        raw = self._cache.get_sync(key)
        if raw is None:
            return None
        return pickle.loads(raw)
    
    def set_sync(self, key: str, value: Any, ttl: int) -> None:
        """Синхронная установка значения в кэш"""
        pickled = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        self._cache.set_sync(key, pickled, ttl)
    
    async def delete(self, key: str) -> None:
        """Удаление ключа из кэша"""
        await self._cache.delete(key)
    
    def delete_sync(self, key: str) -> None:
        """Синхронное удаление ключа из кэша"""
        self._cache.delete_sync(key)
    
    async def cleanup_expired(self) -> int:
        """Очистка истекших записей"""
        return await self._cache.cleanup_expired()
    
    def cleanup_expired_sync(self) -> int:
        """Синхронная очистка истекших записей"""
        return self._cache.cleanup_expired_sync()
    
    async def close(self) -> None:
        """Закрытие кэша"""
        await self._cache.close()
    
    def close_sync(self) -> None:
        """Синхронное закрытие кэша"""
        self._cache.close_sync()

