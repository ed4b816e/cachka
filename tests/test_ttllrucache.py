import pytest
import time
import asyncio
import threading
from cachka.ttllrucache import TTLLRUCache


class TestTTLLRUCacheBasic:
    """Базовые операции TTLLRUCache"""

    def test_get_set(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        assert cache.get("missing") is None
        assert cache.get("missing", default="default") == "default"

    def test_delete(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        cache.delete("key1")
        assert cache.get("key1") is None

    def test_contains(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert "key1" in cache
        assert "missing" not in cache

    def test_len(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        assert len(cache) == 0
        cache.set("key1", "value1")
        assert len(cache) == 1
        cache.set("key2", "value2")
        assert len(cache) == 2

    def test_dict_interface(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        cache["key1"] = "value1"
        assert cache["key1"] == "value1"
        assert "key1" in cache


class TestTTLLRUCacheTTL:
    """Тесты TTL (Time To Live)"""

    def test_ttl_expiration(self):
        cache = TTLLRUCache(maxsize=10, ttl=1)  # 1 second TTL
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        time.sleep(1.1)  # Wait for expiration
        assert cache.get("key1") is None

    def test_ttl_not_expired(self):
        cache = TTLLRUCache(maxsize=10, ttl=10)
        cache.set("key1", "value1")
        time.sleep(0.5)  # Less than TTL
        assert cache.get("key1") == "value1"

    def test_touch_extend_ttl(self):
        cache = TTLLRUCache(maxsize=10, ttl=2)
        cache.set("key1", "value1")
        time.sleep(1.5)
        assert cache.touch("key1") is True
        time.sleep(1.0)  # Total 2.5s, but touched at 1.5s
        assert cache.get("key1") == "value1"  # Still valid

    def test_touch_nonexistent_key(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        assert cache.touch("missing") is False

    def test_get_removes_expired(self):
        cache = TTLLRUCache(maxsize=10, ttl=1)
        cache.set("key1", "value1")
        time.sleep(1.1)
        assert cache.get("key1") is None
        assert "key1" not in cache


class TestTTLLRUCacheLRU:
    """Тесты LRU eviction"""

    def test_lru_eviction(self):
        cache = TTLLRUCache(maxsize=3, ttl=60, shards=1)  # Один шард для предсказуемости
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        assert len(cache) == 3
        
        # Add 4th item, should evict least recently used (key1)
        # key1 был добавлен первым и не использовался после этого
        cache.set("key4", "value4")
        assert len(cache) == 3
        
        # key1 должен быть вытеснен (least recently used)
        assert cache.get("key1") is None
        # Остальные должны остаться
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_get_updates_lru(self):
        cache = TTLLRUCache(maxsize=3, ttl=60, shards=1)  # Один шард для предсказуемости
        # Заполняем кэш
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        
        # Access key1 to make it most recently used
        # Это должно переместить key1 в конец LRU списка
        val = cache.get("key1")
        assert val == "value1"
        
        # Add new item, should evict key2 (least recently used после key1)
        # Порядок LRU: key2 (старый), key3, key1 (обновлен), key4 (новый)
        cache.set("key4", "value4")
        
        # key1 должен остаться (был обновлен через get)
        assert cache.get("key1") == "value1"
        # key2 должен быть вытеснен (least recently used)
        assert cache.get("key2") is None
        # key3 и key4 должны остаться
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_set_updates_lru(self):
        cache = TTLLRUCache(maxsize=3, ttl=60, shards=1)  # Один шард для предсказуемости
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        
        # Update key1 to make it most recently used
        cache.set("key1", "value1_updated")
        
        # Add new item, should evict key2 (least recently used)
        cache.set("key4", "value4")
        assert cache.get("key1") == "value1_updated"  # Still there
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"  # Still there
        assert cache.get("key4") == "value4"  # New item


class TestTTLLRUCacheSharding:
    """Тесты шардирования"""

    def test_shard_distribution(self):
        cache = TTLLRUCache(maxsize=100, ttl=60, shards=4)
        # Add many keys
        for i in range(20):
            cache.set(f"key{i}", f"value{i}")
        
        # Check that keys are distributed across shards
        shard_counts = [len(shard) for shard in cache._shards]
        # At least some keys should be in different shards
        assert max(shard_counts) > 0
        assert sum(shard_counts) == 20

    def test_consistent_shard_selection(self):
        cache = TTLLRUCache(maxsize=10, ttl=60, shards=4)
        key = "test_key"
        shard1 = cache._get_shard(key)
        shard2 = cache._get_shard(key)
        assert shard1 is shard2  # Same shard for same key

    def test_shard_isolation(self):
        cache = TTLLRUCache(maxsize=5, ttl=60, shards=2)
        # Fill first shard
        cache.set("key0", "value0")
        cache.set("key2", "value2")  # Same shard as key0 (if hash % 2 == 0)
        
        # Keys in different shards shouldn't affect each other's eviction
        # This is a basic test - full isolation requires more complex scenario
        assert len(cache) >= 1


class TestTTLLRUCacheGetOrSet:
    """Тесты get_or_set"""

    def test_get_or_set_existing(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        
        call_count = [0]
        def factory():
            call_count[0] += 1
            return "new_value"
        
        result = cache.get_or_set("key1", factory)
        assert result == "value1"
        assert call_count[0] == 0  # Factory not called

    def test_get_or_set_new(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        
        call_count = [0]
        def factory():
            call_count[0] += 1
            return "new_value"
        
        result = cache.get_or_set("key1", factory)
        assert result == "new_value"
        assert call_count[0] == 1  # Factory called once
        assert cache.get("key1") == "new_value"

    def test_get_or_set_thread_safe(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        results = []
        
        def worker():
            def factory():
                return threading.current_thread().name
            result = cache.get_or_set("key1", factory)
            results.append(result)
        
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All should get the same value (first one to set)
        assert len(set(results)) == 1


class TestTTLLRUCacheCleanup:
    """Тесты cleanup"""

    def test_cleanup_expired(self):
        cache = TTLLRUCache(maxsize=10, ttl=1)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        time.sleep(1.1)
        
        removed = cache.cleanup()
        assert removed >= 2
        assert len(cache) == 0

    def test_cleanup_returns_count(self):
        cache = TTLLRUCache(maxsize=10, ttl=1)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        time.sleep(1.1)
        
        removed = cache.cleanup()
        assert isinstance(removed, int)
        assert removed >= 0

    def test_cleanup_partial_expiration(self):
        cache = TTLLRUCache(maxsize=10, ttl=2)
        cache.set("key1", "value1")  # Will expire
        time.sleep(1.0)
        cache.set("key2", "value2")  # Won't expire yet
        time.sleep(1.1)  # key1 expired, key2 still valid
        
        removed = cache.cleanup()
        assert removed >= 1
        assert cache.get("key2") == "value2"  # Still valid


class TestTTLLRUCacheAsync:
    """Тесты async API"""

    @pytest.mark.asyncio
    async def test_get_async(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        result = await cache.get_async("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_set_async(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        await cache.set_async("key1", "value1")
        assert cache.get("key1") == "value1"

    @pytest.mark.asyncio
    async def test_delete_async(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        await cache.delete_async("key1")
        assert cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_touch_async(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        result = await cache.touch_async("key1")
        assert result is True
        assert cache.get("key1") == "value1"

    @pytest.mark.asyncio
    async def test_get_or_set_async(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        
        async def factory():
            await asyncio.sleep(0.01)
            return "async_value"
        
        result = await cache.get_or_set_async("key1", factory)
        assert result == "async_value"
        assert cache.get("key1") == "async_value"


class TestTTLLRUCacheBackgroundCleanup:
    """Тесты фоновой очистки"""

    @pytest.mark.asyncio
    async def test_background_cleanup_start_stop(self):
        cache = TTLLRUCache(maxsize=10, ttl=1)
        cache.set("key1", "value1")
        
        await cache.start_background_cleanup(interval=1)
        assert cache._bg_task is not None
        
        time.sleep(1.5)  # Wait for cleanup
        await asyncio.sleep(0.5)  # Give cleanup time to run
        
        await cache.stop_background_cleanup()
        assert cache._bg_task is None

    @pytest.mark.asyncio
    async def test_background_cleanup_requires_async(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        # Should work in async context
        await cache.start_background_cleanup(interval=60)
        await cache.stop_background_cleanup()


class TestTTLLRUCacheEdgeCases:
    """Edge cases"""

    def test_zero_maxsize_raises(self):
        with pytest.raises(ValueError, match="maxsize must be > 0"):
            TTLLRUCache(maxsize=0, ttl=60)

    def test_negative_ttl_raises(self):
        with pytest.raises(ValueError, match="ttl must be > 0"):
            TTLLRUCache(maxsize=10, ttl=-1)

    def test_zero_shards_raises(self):
        with pytest.raises(ValueError, match="shards must be > 0"):
            TTLLRUCache(maxsize=10, ttl=60, shards=0)

    def test_unicode_keys(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        cache.set("ключ", "значение")
        cache.set("🔑", "emoji")
        assert cache.get("ключ") == "значение"
        assert cache.get("🔑") == "emoji"

    def test_none_value(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        cache.set("key1", None)
        assert cache.get("key1") is None

    def test_complex_objects(self):
        cache = TTLLRUCache(maxsize=10, ttl=60)
        obj = {"nested": {"list": [1, 2, 3]}}
        cache.set("key1", obj)
        result = cache.get("key1")
        assert result == obj
        assert result["nested"]["list"] == [1, 2, 3]


class TestTTLLRUCacheThreadSafety:
    """Тесты потокобезопасности"""

    def test_concurrent_get_set(self):
        cache = TTLLRUCache(maxsize=100, ttl=60)
        errors = []
        
        def worker(i):
            try:
                for j in range(10):
                    key = f"key_{i}_{j}"
                    cache.set(key, f"value_{i}_{j}")
                    assert cache.get(key) == f"value_{i}_{j}"
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(cache) <= 100  # Should respect maxsize

    def test_concurrent_delete(self):
        cache = TTLLRUCache(maxsize=100, ttl=60)
        # Pre-populate
        for i in range(50):
            cache.set(f"key{i}", f"value{i}")
        
        def worker():
            for i in range(50):
                cache.delete(f"key{i}")
        
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All should be deleted
        assert len(cache) == 0

