"""
SQLite кэш: реализация, конфигурация и адаптер.
"""

import asyncio
import dataclasses
import os
import pickle
import sqlite3
import threading
import time
from abc import (
    ABC,
    abstractmethod,
)
from contextlib import (
    asynccontextmanager,
    contextmanager,
)
from typing import (
    Any,
    Optional,
)

import aiosqlite

from cachka.interface import ICache

# === Optional deps ===
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

# === Config ===


@dataclasses.dataclass
class SQLiteCacheConfig:
    """Конфигурация для SQLite кэша"""

    db_path: str = "cache.db"
    enable_encryption: bool = False
    encryption_key: Optional[str] = None  # base64-encoded 32-byte key
    max_key_length: int = 512


# === Storage Backend ===


class StorageBackend(ABC):
    """Абстрактный базовый класс для бэкендов хранения"""

    @abstractmethod
    async def get(self, key: str) -> Optional[bytes]: ...
    @abstractmethod
    async def set(self, key: str, value: bytes, ttl: int) -> None: ...
    @abstractmethod
    async def cleanup_expired(self) -> int: ...
    @abstractmethod
    async def close(self) -> None: ...


# === Implementation ===


class SQLiteStorage(StorageBackend):
    """Реализация SQLite хранилища для кэша"""

    def __init__(self, db_path: str, config: SQLiteCacheConfig):
        self.db_path = db_path
        self.config = config
        self._connection: Optional[aiosqlite.Connection] = None
        self._sync_connection: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()
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

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL,
                expires_at REAL NOT NULL
            )
        """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)"
        )

    @staticmethod
    def _init_db_sync(conn: sqlite3.Connection):
        """Синхронная инициализация БД"""
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-10000")
        conn.execute("PRAGMA temp_store=MEMORY")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value BLOB NOT NULL,
                expires_at REAL NOT NULL
            )
        """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)")
        conn.commit()

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

    @contextmanager
    def _get_sync_connection(self):
        """Синхронный context manager для получения соединения"""
        with self._sync_lock:
            if self._sync_connection is None:
                self._sync_connection = sqlite3.connect(
                    self.db_path, timeout=30.0, check_same_thread=False
                )
                self._init_db_sync(self._sync_connection)
            yield self._sync_connection

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
                (key, encrypted, expires_at),
            )
            await conn.commit()

    async def cleanup_expired(self) -> int:
        now = time.time()
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM cache WHERE expires_at <= ?", (now,)
            )
            await conn.commit()
            return cursor.rowcount

    async def close(self):
        """Закрывает оба соединения (async и sync)"""
        if self._connection:
            await self._connection.close()
            self._connection = None
        with self._sync_lock:
            if self._sync_connection:
                self._sync_connection.close()
                self._sync_connection = None

    # === Синхронные методы (нативная реализация) ===

    def get_sync(self, key: str) -> Optional[bytes]:
        """Синхронное получение значения из кэша"""
        now = time.time()
        with self._get_sync_connection() as conn:
            cursor = conn.execute(
                "SELECT value FROM cache WHERE key = ? AND expires_at > ?", (key, now)
            )
            row = cursor.fetchone()
            if row and row[0] is not None:
                return self._decrypt(row[0])
            return None

    def set_sync(self, key: str, value: bytes, ttl: int) -> None:
        """Синхронная установка значения в кэш"""
        expires_at = time.time() + ttl
        encrypted = self._encrypt(value)
        with self._get_sync_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, encrypted, expires_at),
            )
            conn.commit()

    def cleanup_expired_sync(self) -> int:
        """Синхронная очистка истекших записей"""
        now = time.time()
        with self._get_sync_connection() as conn:
            cursor = conn.execute("DELETE FROM cache WHERE expires_at <= ?", (now,))
            conn.commit()
            return cursor.rowcount

    def close_sync(self) -> None:
        """Синхронное закрытие соединения"""
        with self._sync_lock:
            if self._sync_connection:
                self._sync_connection.close()
                self._sync_connection = None


# === Adapter ===


class SQLiteStorageAdapter(ICache):
    """
    Адаптер для SQLiteStorage, реализующий интерфейс ICache.

    SQLiteStorage работает с bytes (сериализованными данными),
    этот адаптер добавляет pickle сериализацию/десериализацию.
    """

    def __init__(self, storage: SQLiteStorage):
        self._storage = storage

    async def get(self, key: str) -> Optional[Any]:
        """Асинхронное получение значения из кэша"""
        raw = await self._storage.get(key)
        if raw is None:
            return None
        return pickle.loads(raw)

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Асинхронная установка значения в кэш"""
        pickled = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        await self._storage.set(key, pickled, ttl)

    def get_sync(self, key: str) -> Optional[Any]:
        """Синхронное получение значения из кэша"""
        raw = self._storage.get_sync(key)
        if raw is None:
            return None
        return pickle.loads(raw)

    def set_sync(self, key: str, value: Any, ttl: int) -> None:
        """Синхронная установка значения в кэш"""
        pickled = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
        self._storage.set_sync(key, pickled, ttl)

    async def delete(self, key: str) -> None:
        """Удаление ключа из кэша"""
        # SQLiteStorage не имеет метода delete, используем set с истекшим TTL
        await self._storage.set(key, b"", ttl=0)

    def delete_sync(self, key: str) -> None:
        """Синхронное удаление ключа из кэша"""
        self._storage.set_sync(key, b"", ttl=0)

    async def cleanup_expired(self) -> int:
        """Очистка истекших записей"""
        return await self._storage.cleanup_expired()

    def cleanup_expired_sync(self) -> int:
        """Синхронная очистка истекших записей"""
        return self._storage.cleanup_expired_sync()

    async def close(self) -> None:
        """Закрытие кэша"""
        await self._storage.close()

    def close_sync(self) -> None:
        """Синхронное закрытие кэша"""
        self._storage.close_sync()
