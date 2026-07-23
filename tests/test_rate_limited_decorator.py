"""
Tests for cache.init_rate_limiter + @rate_limited(tag=...).
"""

from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)

import pytest

from cachka import (
    CacheConfig,
    MemoryRateLimiter,
    cache_registry,
    rate_limited,
)
from cachka.rediscache import RedisCacheConfig
from cachka.rate_limiter import (
    RateLimitExceeded,
    RateLimiter,
    RateLimiterConfig,
)


@pytest.fixture(autouse=True)
async def _reset_registry():
    if cache_registry.is_initialized():
        try:
            await cache_registry.shutdown()
        except Exception:
            pass
        cache_registry.reset()
    yield
    if cache_registry.is_initialized():
        try:
            await cache_registry.shutdown()
        except Exception:
            pass
        cache_registry.reset()


def _init_plain_cache():
    cache_registry.initialize(
        CacheConfig(
            cache_layers=["memory"],
            vacuum_interval=None,
            cleanup_on_start=False,
        )
    )
    return cache_registry.get()


def test_init_rate_limiter_memory_backend() -> None:
    cache = _init_plain_cache()
    cache.init_rate_limiter(
        {
            "wikidata_request": RateLimiterConfig(max_requests=60, window_seconds=60),
            "tg": RateLimiterConfig(max_requests=10, window_seconds=1),
        },
        backend="memory",
    )

    assert cache.list_rate_limiter_tags() == ["tg", "wikidata_request"]
    wd = cache.get_rate_limiter("wikidata_request")
    assert isinstance(wd, MemoryRateLimiter)
    assert wd._max_requests == 60
    assert wd._key_prefix == "rate_limit:wikidata_request"


def test_init_rate_limiter_redis_backend_requires_config() -> None:
    cache = _init_plain_cache()
    with pytest.raises(ValueError, match="redis=RedisCacheConfig"):
        cache.init_rate_limiter(
            {"wikidata_request": RateLimiterConfig(max_requests=1, window_seconds=1)},
            backend="redis",
        )


def test_init_rate_limiter_redis_backend_with_stubbed_client() -> None:
    cache = _init_plain_cache()
    redis_session = MagicMock()
    redis_cfg = RedisCacheConfig(host="localhost", port=6379)

    with patch("cachka.core.RedisCache") as redis_cache_cls:
        instance = MagicMock()
        instance.get_async_client = MagicMock(return_value=redis_session)
        redis_cache_cls.return_value = instance

        cache.init_rate_limiter(
            {"wikidata_request": RateLimiterConfig(max_requests=60, window_seconds=60)},
            backend="redis",
            redis=redis_cfg,
        )

    limiter = cache.get_rate_limiter("wikidata_request")
    assert isinstance(limiter, RateLimiter)
    assert limiter._max_requests == 60
    assert limiter._key_prefix == "rate_limit:wikidata_request"
    redis_cache_cls.assert_called_once_with(redis_cfg)


def test_get_rate_limiter_unknown_tag() -> None:
    cache = _init_plain_cache()
    cache.init_rate_limiter(
        {"wikidata_request": RateLimiterConfig(max_requests=1, window_seconds=1)},
        backend="memory",
    )
    with pytest.raises(KeyError, match="Unknown rate limiter tag"):
        cache.get_rate_limiter("missing")


@pytest.mark.asyncio
async def test_rate_limited_decorator_allows_when_slot_free() -> None:
    cache = _init_plain_cache()
    cache.init_rate_limiter(
        {"wikidata_request": RateLimiterConfig(max_requests=5, window_seconds=60)},
        backend="memory",
    )

    limiter = cache.get_rate_limiter("wikidata_request")
    with patch.object(
        limiter, "wait_until_allowed", new_callable=AsyncMock, return_value=True
    ) as wait_mock:

        @rate_limited(tag="wikidata_request")
        async def fetch() -> str:
            return "ok"

        assert await fetch() == "ok"
        wait_mock.assert_awaited_once_with(identifier="default")


@pytest.mark.asyncio
async def test_rate_limited_decorator_raises_when_blocked() -> None:
    cache = _init_plain_cache()
    cache.init_rate_limiter(
        {
            "wikidata_request": RateLimiterConfig(
                max_requests=1,
                window_seconds=60,
                max_wait_sec=0.05,
                poll_interval_sec=0.01,
            )
        },
        backend="memory",
    )

    limiter = cache.get_rate_limiter("wikidata_request")
    with patch.object(
        limiter, "wait_until_allowed", new_callable=AsyncMock, return_value=False
    ):

        @rate_limited(tag="wikidata_request")
        async def fetch() -> str:
            return "ok"

        with pytest.raises(RateLimitExceeded) as exc:
            await fetch()
        assert exc.value.tag == "wikidata_request"


@pytest.mark.asyncio
async def test_rate_limited_wait_false_checks_once() -> None:
    cache = _init_plain_cache()
    cache.init_rate_limiter(
        {"wikidata_request": RateLimiterConfig(max_requests=5, window_seconds=60)},
        backend="memory",
    )
    limiter = cache.get_rate_limiter("wikidata_request")

    with patch.object(
        limiter, "is_request_allowed", new_callable=AsyncMock, return_value=True
    ) as check_mock:

        @rate_limited(tag="wikidata_request", wait=False)
        async def fetch() -> str:
            return "ok"

        assert await fetch() == "ok"
        check_mock.assert_awaited_once_with(identifier="default")


def test_rate_limited_rejects_sync_functions() -> None:
    with pytest.raises(TypeError, match="async functions only"):

        @rate_limited(tag="wikidata_request")
        def sync_fetch() -> str:
            return "nope"


def test_init_rate_limiter_invalid_backend() -> None:
    cache = _init_plain_cache()
    with pytest.raises(ValueError, match="Unsupported rate limiter backend"):
        cache.init_rate_limiter(
            {"wikidata_request": RateLimiterConfig(max_requests=1, window_seconds=1)},
            backend="sqlite",
        )
