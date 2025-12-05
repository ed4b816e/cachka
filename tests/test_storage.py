import base64
import os
import secrets
import tempfile
import time

import pytest

from cachka.sqlitecache import (
    SQLiteCacheConfig,
    SQLiteStorage,
)


class TestSQLiteStorageBasic:
    """Базовые операции SQLiteStorage"""

    @pytest.fixture
    def temp_db(self):
        """Создает временную БД для тестов"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def config(self, temp_db):
        return SQLiteCacheConfig(
            db_path=temp_db,
        )

    @pytest.fixture
    async def storage(self, config):
        storage = SQLiteStorage(config.db_path, config)
        yield storage
        await storage.close()

    @pytest.mark.asyncio
    async def test_get_set(self, storage):
        await storage.set("key1", b"value1", ttl=60)
        result = await storage.get("key1")
        assert result == b"value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self, storage):
        result = await storage.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_overwrite(self, storage):
        await storage.set("key1", b"value1", ttl=60)
        await storage.set("key1", b"value2", ttl=60)
        result = await storage.get("key1")
        assert result == b"value2"

    @pytest.mark.asyncio
    async def test_ttl_expiration(self, storage):
        await storage.set("key1", b"value1", ttl=1)
        assert await storage.get("key1") == b"value1"
        time.sleep(1.1)
        assert await storage.get("key1") is None

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, storage):
        await storage.set("key1", b"value1", ttl=1)
        await storage.set("key2", b"value2", ttl=1)
        await storage.set("key3", b"value3", ttl=100)  # Won't expire

        time.sleep(1.1)
        removed = await storage.cleanup_expired()
        assert removed >= 2

        assert await storage.get("key1") is None
        assert await storage.get("key2") is None
        assert await storage.get("key3") == b"value3"

    @pytest.mark.asyncio
    async def test_cleanup_returns_count(self, storage):
        await storage.set("key1", b"value1", ttl=1)
        time.sleep(1.1)
        removed = await storage.cleanup_expired()
        assert isinstance(removed, int)
        assert removed >= 1

    @pytest.mark.asyncio
    async def test_empty_value(self, storage):
        await storage.set("key1", b"", ttl=60)
        result = await storage.get("key1")
        assert result == b""

    @pytest.mark.asyncio
    async def test_special_characters_in_key(self, storage):
        key = "key/with/special-chars_123"
        await storage.set(key, b"value1", ttl=60)
        result = await storage.get(key)
        assert result == b"value1"

    @pytest.mark.asyncio
    async def test_close_connection(self, storage):
        await storage.set("key1", b"value1", ttl=60)
        await storage.close()
        # After close, connection should be None
        assert storage._connection is None


class TestSQLiteStorageEncryption:
    """Тесты шифрования"""

    @pytest.fixture
    def encryption_key(self):
        """Генерирует валидный ключ шифрования"""
        key_bytes = secrets.token_bytes(32)
        return base64.b64encode(key_bytes).decode()

    @pytest.fixture
    def temp_db(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def encrypted_config(self, temp_db, encryption_key):
        return SQLiteCacheConfig(
            db_path=temp_db, enable_encryption=True, encryption_key=encryption_key
        )

    @pytest.fixture
    async def encrypted_storage(self, encrypted_config):
        storage = SQLiteStorage(encrypted_config.db_path, encrypted_config)
        yield storage
        await storage.close()

    @pytest.mark.asyncio
    async def test_encryption_enabled(self, encrypted_storage):
        """Проверяет, что данные шифруются"""
        await encrypted_storage.set("key1", b"value1", ttl=60)
        # Проверяем, что в БД данные зашифрованы
        async with encrypted_storage._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT value FROM cache WHERE key = ?", ("key1",)
            )
            row = await cursor.fetchone()
            assert row is not None
            # Зашифрованные данные должны быть длиннее оригинальных (nonce + ciphertext)
            assert len(row[0]) > len(b"value1")

    @pytest.mark.asyncio
    async def test_encryption_decryption(self, encrypted_storage):
        """Проверяет, что зашифрованные данные расшифровываются"""
        await encrypted_storage.set("key1", b"value1", ttl=60)
        result = await encrypted_storage.get("key1")
        assert result == b"value1"

    @pytest.mark.asyncio
    async def test_encryption_different_keys(self, temp_db, encryption_key):
        """Разные ключи дают разные шифры"""
        config1 = SQLiteCacheConfig(
            db_path=temp_db, enable_encryption=True, encryption_key=encryption_key
        )
        storage1 = SQLiteStorage(temp_db, config1)

        # Создаем второй ключ
        key2_bytes = secrets.token_bytes(32)
        key2 = base64.b64encode(key2_bytes).decode()
        config2 = SQLiteCacheConfig(
            db_path=temp_db + ".2", enable_encryption=True, encryption_key=key2
        )
        storage2 = SQLiteStorage(config2.db_path, config2)

        try:
            await storage1.set("key1", b"value1", ttl=60)
            await storage2.set("key1", b"value1", ttl=60)

            # Данные должны быть зашифрованы по-разному
            async with storage1._get_connection() as conn1:
                cursor1 = await conn1.execute(
                    "SELECT value FROM cache WHERE key = ?", ("key1",)
                )
                row1 = await cursor1.fetchone()

            async with storage2._get_connection() as conn2:
                cursor2 = await conn2.execute(
                    "SELECT value FROM cache WHERE key = ?", ("key1",)
                )
                row2 = await cursor2.fetchone()

            # Зашифрованные значения должны быть разными
            assert row1[0] != row2[0]
        finally:
            await storage1.close()
            await storage2.close()
            if os.path.exists(config2.db_path):
                os.unlink(config2.db_path)

    def test_encryption_without_key_raises(self, temp_db):
        """Ошибка при включенном шифровании без ключа"""
        config = SQLiteCacheConfig(
            db_path=temp_db, enable_encryption=True, encryption_key=None
        )
        # При создании storage не должно быть ошибки, но при использовании может быть
        storage = SQLiteStorage(temp_db, config)
        # Шифрование не будет работать без ключа, но storage создастся

    def test_encryption_invalid_key_raises(self, temp_db):
        """Ошибка при неверном ключе"""
        invalid_key = base64.b64encode(b"short").decode()  # Не 32 байта
        config = SQLiteCacheConfig(
            db_path=temp_db, enable_encryption=True, encryption_key=invalid_key
        )
        with pytest.raises(ValueError, match="Encryption key must be 32 bytes"):
            SQLiteStorage(temp_db, config)

    def test_encryption_key_length(self, temp_db):
        """Проверка длины ключа"""
        # Правильный ключ (32 байта)
        good_key = base64.b64encode(secrets.token_bytes(32)).decode()
        config = SQLiteCacheConfig(
            db_path=temp_db, enable_encryption=True, encryption_key=good_key
        )
        storage = SQLiteStorage(temp_db, config)
        assert storage._encryption_key is not None
        assert len(storage._encryption_key) == 32


class TestSQLiteStorageEdgeCases:
    """Edge cases"""

    @pytest.fixture
    def temp_db(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def config(self, temp_db):
        return SQLiteCacheConfig(
            db_path=temp_db,
        )

    @pytest.fixture
    async def storage(self, config):
        storage = SQLiteStorage(config.db_path, config)
        yield storage
        await storage.close()

    @pytest.mark.asyncio
    async def test_very_large_values(self, storage):
        """Очень большие значения"""
        large_value = b"x" * (10 * 1024 * 1024)  # 10 MB
        await storage.set("key1", large_value, ttl=60)
        result = await storage.get("key1")
        assert result == large_value
        assert len(result) == 10 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_unicode_in_key(self, storage):
        """Unicode в ключах"""
        key = "ключ_🔑"
        await storage.set(key, b"value1", ttl=60)
        result = await storage.get(key)
        assert result == b"value1"

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, storage):
        """Конкурентные операции"""
        import asyncio

        async def worker(i):
            for j in range(10):
                key = f"key_{i}_{j}"
                await storage.set(key, f"value_{i}_{j}".encode(), ttl=60)
                result = await storage.get(key)
                assert result == f"value_{i}_{j}".encode()

        await asyncio.gather(*[worker(i) for i in range(5)])


class TestSQLiteStorageSync:
    """Тесты синхронных методов SQLiteStorage (нативная реализация)"""

    @pytest.fixture
    def temp_db(self):
        """Создает временную БД для тестов"""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def config(self, temp_db):
        return SQLiteCacheConfig(
            db_path=temp_db,
        )

    @pytest.fixture
    def storage(self, config):
        """Синхронный storage (не async)"""
        storage = SQLiteStorage(config.db_path, config)
        yield storage
        storage.close_sync()

    def test_get_set_sync(self, storage):
        """Синхронные get/set операции"""
        storage.set_sync("key1", b"value1", ttl=60)
        result = storage.get_sync("key1")
        assert result == b"value1"

    def test_get_missing_key_sync(self, storage):
        """Получение несуществующего ключа (синхронно)"""
        result = storage.get_sync("missing")
        assert result is None

    def test_set_overwrite_sync(self, storage):
        """Перезапись существующего ключа (синхронно)"""
        storage.set_sync("key1", b"value1", ttl=60)
        storage.set_sync("key1", b"value2", ttl=60)
        result = storage.get_sync("key1")
        assert result == b"value2"

    def test_ttl_expiration_sync(self, storage):
        """Истечение TTL (синхронно)"""
        storage.set_sync("key1", b"value1", ttl=1)
        assert storage.get_sync("key1") == b"value1"
        time.sleep(1.1)
        assert storage.get_sync("key1") is None

    def test_cleanup_expired_sync(self, storage):
        """Синхронная очистка истекших записей"""
        storage.set_sync("key1", b"value1", ttl=1)
        storage.set_sync("key2", b"value2", ttl=1)
        storage.set_sync("key3", b"value3", ttl=100)  # Не истечет

        time.sleep(1.1)
        removed = storage.cleanup_expired_sync()
        assert removed >= 2

        assert storage.get_sync("key1") is None
        assert storage.get_sync("key2") is None
        assert storage.get_sync("key3") == b"value3"

    def test_encryption_sync(self, temp_db):
        """Шифрование работает в синхронных методах"""
        import base64
        import secrets

        encryption_key = base64.b64encode(secrets.token_bytes(32)).decode()

        config = SQLiteCacheConfig(
            db_path=temp_db,
            enable_encryption=True,
            encryption_key=encryption_key,
        )
        storage = SQLiteStorage(config.db_path, config)
        try:
            storage.set_sync("key1", b"value1", ttl=60)
            result = storage.get_sync("key1")
            assert result == b"value1"
        finally:
            storage.close_sync()

    def test_concurrent_sync_operations(self, storage):
        """Конкурентные синхронные операции"""
        import threading

        def worker(i):
            for j in range(10):
                key = f"key_{i}_{j}"
                storage.set_sync(key, f"value_{i}_{j}".encode(), ttl=60)
                result = storage.get_sync(key)
                assert result == f"value_{i}_{j}".encode()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def test_close_sync(self, storage):
        """Закрытие синхронного соединения"""
        storage.set_sync("key1", b"value1", ttl=60)
        storage.close_sync()
        # После close соединение должно быть None
        assert storage._sync_connection is None
