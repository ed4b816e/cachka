"""
Unit tests for Redis RateLimiter (mocked Redis, no container required).
"""

from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
)

import pytest

from cachka.rate_limiter import (
    MemoryRateLimiter,
    RateLimiter,
    RateLimiterConfig,
)


@pytest.fixture
def redis_session() -> MagicMock:
    session = MagicMock()
    session.pipeline = MagicMock()
    return session


@pytest.fixture
def rate_limiter(redis_session: MagicMock) -> RateLimiter:
    return RateLimiter(
        redis_session=redis_session,
        max_requests=2,
        window_seconds=60,
        key_prefix="rate_limit:test",
    )


@pytest.mark.asyncio
async def test_is_request_allowed_when_under_limit(
    rate_limiter: RateLimiter,
    redis_session: MagicMock,
) -> None:
    pipe = MagicMock()
    pipe.zremrangebyscore = AsyncMock()
    pipe.zcard = AsyncMock()
    pipe.execute = AsyncMock(return_value=[0, 0])
    redis_session.pipeline = MagicMock(return_value=pipe)
    redis_session.zadd = AsyncMock()
    redis_session.expire = AsyncMock()

    assert await rate_limiter.is_request_allowed("id-1") is True
    redis_session.zadd.assert_awaited_once()
    redis_session.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_is_request_allowed_when_limit_exceeded(
    rate_limiter: RateLimiter,
    redis_session: MagicMock,
) -> None:
    pipe = MagicMock()
    pipe.zremrangebyscore = AsyncMock()
    pipe.zcard = AsyncMock()
    pipe.execute = AsyncMock(return_value=[0, 2])
    redis_session.pipeline = MagicMock(return_value=pipe)
    redis_session.zadd = AsyncMock()

    assert await rate_limiter.is_request_allowed("id-1") is False
    redis_session.zadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_is_request_allowed_fail_open_on_redis_error(
    rate_limiter: RateLimiter,
    redis_session: MagicMock,
) -> None:
    from redis.exceptions import ConnectionError as RedisConnectionError

    redis_session.pipeline = MagicMock(side_effect=RedisConnectionError("down"))

    assert await rate_limiter.is_request_allowed("id-1") is True


@pytest.mark.asyncio
async def test_wait_until_allowed_succeeds_immediately(
    rate_limiter: RateLimiter,
) -> None:
    with patch.object(
        rate_limiter, "is_request_allowed", new_callable=AsyncMock, return_value=True
    ) as mock_allowed:
        result = await rate_limiter.wait_until_allowed(
            identifier="acc-1", max_wait_sec=1.0, poll_interval_sec=0.01
        )

    assert result is True
    mock_allowed.assert_awaited_once()


@pytest.mark.asyncio
async def test_wait_until_allowed_times_out(rate_limiter: RateLimiter) -> None:
    with patch.object(
        rate_limiter, "is_request_allowed", new_callable=AsyncMock, return_value=False
    ):
        result = await rate_limiter.wait_until_allowed(
            identifier="acc-1", max_wait_sec=0.05, poll_interval_sec=0.02
        )

    assert result is False


@pytest.mark.asyncio
async def test_get_remaining_requests(
    rate_limiter: RateLimiter,
    redis_session: MagicMock,
) -> None:
    pipe = MagicMock()
    pipe.zremrangebyscore = AsyncMock()
    pipe.zcard = AsyncMock()
    pipe.execute = AsyncMock(return_value=[0, 1])
    redis_session.pipeline = MagicMock(return_value=pipe)

    assert await rate_limiter.get_remaining_requests("id-1") == 1


@pytest.mark.asyncio
async def test_reset_limits(
    rate_limiter: RateLimiter,
    redis_session: MagicMock,
) -> None:
    redis_session.delete = AsyncMock(return_value=1)

    assert await rate_limiter.reset_limits("id-1") is True
    redis_session.delete.assert_awaited_once_with("rate_limit:test:id-1")


def test_config_overrides_constructor_args(redis_session: MagicMock) -> None:
    config = RateLimiterConfig(
        max_requests=10,
        window_seconds=30,
        key_prefix="rl:",
        max_wait_sec=5.0,
        poll_interval_sec=0.1,
    )
    limiter = RateLimiter(redis_session=redis_session, max_requests=999, config=config)

    assert limiter._max_requests == 10
    assert limiter._window_seconds == 30
    assert limiter._key_prefix == "rl:"
    assert limiter._default_max_wait_sec == 5.0
    assert limiter._default_poll_interval_sec == 0.1


@pytest.mark.asyncio
async def test_memory_rate_limiter_blocks_after_max() -> None:
    limiter = MemoryRateLimiter(max_requests=2, window_seconds=60, key_prefix="rl:test")
    assert await limiter.is_request_allowed("default") is True
    assert await limiter.is_request_allowed("default") is True
    assert await limiter.is_request_allowed("default") is False
    assert await limiter.get_remaining_requests("default") == 0
    assert await limiter.reset_limits("default") is True
    assert await limiter.is_request_allowed("default") is True
