"""
Rate limiters: Redis (distributed) and in-memory (single process).

Redis backend requires: pip install cachka[redis]
"""

from __future__ import annotations

import asyncio
import dataclasses
import time
from typing import (
    Optional,
    Protocol,
)

import structlog

logger = structlog.get_logger(__name__)

try:
    from redis import asyncio as aioredis
    from redis.exceptions import ConnectionError as RedisConnectionError

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    aioredis = None  # type: ignore[assignment]
    RedisConnectionError = ConnectionError  # type: ignore[misc, assignment]


@dataclasses.dataclass
class RateLimiterConfig:
    """Configuration for sliding-window rate limiter profiles."""

    max_requests: int = 60
    window_seconds: int = 60
    key_prefix: str = "rate_limit:"
    max_wait_sec: float = 15.0
    poll_interval_sec: float = 0.3


class RateLimitExceeded(Exception):
    """Raised by @rate_limited when the quota is exhausted (or wait timed out)."""

    def __init__(self, tag: str, identifier: str = "default") -> None:
        self.tag = tag
        self.identifier = identifier
        super().__init__(
            f"Rate limit exceeded for tag={tag!r}, identifier={identifier!r}"
        )


class RateLimiterLike(Protocol):
    async def is_request_allowed(self, identifier: str = "default") -> bool: ...

    async def wait_until_allowed(
        self,
        identifier: str = "default",
        *,
        max_wait_sec: Optional[float] = None,
        poll_interval_sec: Optional[float] = None,
    ) -> bool: ...

    async def get_remaining_requests(self, identifier: str = "default") -> Optional[int]: ...

    async def reset_limits(self, identifier: str = "default") -> bool: ...


def _apply_config(
    config: Optional[RateLimiterConfig],
    max_requests: int,
    window_seconds: int,
    key_prefix: str,
) -> tuple[int, int, str, float, float]:
    if config is not None:
        return (
            config.max_requests,
            config.window_seconds,
            config.key_prefix,
            config.max_wait_sec,
            config.poll_interval_sec,
        )
    return max_requests, window_seconds, key_prefix, 15.0, 0.3


class _WaitMixin:
    _default_max_wait_sec: float
    _default_poll_interval_sec: float

    async def is_request_allowed(self, identifier: str = "default") -> bool:
        raise NotImplementedError

    async def wait_until_allowed(
        self,
        identifier: str = "default",
        *,
        max_wait_sec: Optional[float] = None,
        poll_interval_sec: Optional[float] = None,
    ) -> bool:
        if max_wait_sec is None:
            max_wait_sec = self._default_max_wait_sec
        if poll_interval_sec is None:
            poll_interval_sec = self._default_poll_interval_sec

        deadline = time.monotonic() + max_wait_sec
        while time.monotonic() < deadline:
            if await self.is_request_allowed(identifier=identifier):
                return True
            await asyncio.sleep(poll_interval_sec)

        logger.warning(
            "rate_limit_wait_timeout",
            identifier=identifier,
            max_wait_sec=max_wait_sec,
        )
        return False


class MemoryRateLimiter(_WaitMixin):
    """
    In-process sliding-window rate limiter.

    Not shared across workers/pods — use Redis backend in production.
    """

    def __init__(
        self,
        max_requests: int = 60,
        window_seconds: int = 60,
        key_prefix: str = "rate_limit:",
        *,
        config: Optional[RateLimiterConfig] = None,
    ) -> None:
        (
            max_requests,
            window_seconds,
            key_prefix,
            max_wait_sec,
            poll_interval_sec,
        ) = _apply_config(config, max_requests, window_seconds, key_prefix)

        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._key_prefix = key_prefix
        self._default_max_wait_sec = max_wait_sec
        self._default_poll_interval_sec = poll_interval_sec
        self._buckets: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    def _key(self, identifier: str) -> str:
        return f"{self._key_prefix}:{identifier}"

    async def is_request_allowed(self, identifier: str = "default") -> bool:
        async with self._lock:
            current_time = time.time()
            window_start = current_time - self._window_seconds
            key = self._key(identifier)
            stamps = [t for t in self._buckets.get(key, []) if t > window_start]
            if len(stamps) >= self._max_requests:
                self._buckets[key] = stamps
                logger.warning(
                    "rate_limit_exceeded",
                    identifier=identifier,
                    current_count=len(stamps),
                    max_requests=self._max_requests,
                    backend="memory",
                )
                return False
            stamps.append(current_time)
            self._buckets[key] = stamps
            logger.debug(
                "rate_limit_allowed",
                identifier=identifier,
                current_count=len(stamps),
                max_requests=self._max_requests,
                backend="memory",
            )
            return True

    async def get_remaining_requests(self, identifier: str = "default") -> Optional[int]:
        async with self._lock:
            current_time = time.time()
            window_start = current_time - self._window_seconds
            key = self._key(identifier)
            stamps = [t for t in self._buckets.get(key, []) if t > window_start]
            self._buckets[key] = stamps
            return max(0, self._max_requests - len(stamps))

    async def reset_limits(self, identifier: str = "default") -> bool:
        async with self._lock:
            self._buckets.pop(self._key(identifier), None)
            logger.info("rate_limit_reset", identifier=identifier, backend="memory")
            return True


class RateLimiter(_WaitMixin):
    """
    Rate limiter using Redis sliding window algorithm.

    Limits requests per time window across multiple replicas.
    Uses Redis pipeline for efficient batching of commands.
    Minor race conditions are acceptable for rate limiting use case.
    """

    def __init__(
        self,
        redis_session: "aioredis.Redis",
        max_requests: int = 60,
        window_seconds: int = 60,
        key_prefix: str = "rate_limit:",
        *,
        config: Optional[RateLimiterConfig] = None,
    ) -> None:
        if not HAS_REDIS:
            raise ImportError(
                "Redis is not installed. To use RateLimiter, install it with:\n"
                "  pip install redis\n"
                "or\n"
                "  pip install cachka[redis]"
            )

        (
            max_requests,
            window_seconds,
            key_prefix,
            max_wait_sec,
            poll_interval_sec,
        ) = _apply_config(config, max_requests, window_seconds, key_prefix)

        self._redis_session = redis_session
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._key_prefix = key_prefix
        self._default_max_wait_sec = max_wait_sec
        self._default_poll_interval_sec = poll_interval_sec

    async def is_request_allowed(self, identifier: str = "default") -> bool:
        """
        Check if request is allowed for given identifier.

        On Redis errors returns True (fail-open).
        """
        try:
            # Do not `async with` the client — that closes the shared connection.
            redis = self._redis_session
            current_time = time.time()
            window_start = int(current_time) - self._window_seconds
            key = f"{self._key_prefix}:{identifier}"

            pipe = redis.pipeline()
            await pipe.zremrangebyscore(key, 0, window_start)
            await pipe.zcard(key)
            results = await pipe.execute()
            current_count = results[1]

            if current_count >= self._max_requests:
                logger.warning(
                    "rate_limit_exceeded",
                    identifier=identifier,
                    current_count=current_count,
                    max_requests=self._max_requests,
                    backend="redis",
                )
                return False

            await redis.zadd(key, {str(current_time): current_time})
            await redis.expire(key, self._window_seconds + 60)

            logger.debug(
                "rate_limit_allowed",
                identifier=identifier,
                current_count=current_count + 1,
                max_requests=self._max_requests,
                backend="redis",
            )
            return True

        except RedisConnectionError as e:
            logger.error(
                "rate_limit_redis_error",
                error=str(e),
                action="allow_by_default",
            )
            return True
        except Exception as e:
            logger.error(
                "rate_limit_unexpected_error",
                error=str(e),
                action="allow_by_default",
            )
            return True

    async def get_remaining_requests(self, identifier: str = "default") -> Optional[int]:
        try:
            redis = self._redis_session
            current_time = int(time.time())
            window_start = current_time - self._window_seconds
            key = f"{self._key_prefix}:{identifier}"

            pipe = redis.pipeline()
            await pipe.zremrangebyscore(key, 0, window_start)
            await pipe.zcard(key)
            results = await pipe.execute()
            current_count = results[1]

            remaining = max(0, self._max_requests - current_count)
            logger.debug(
                "rate_limit_remaining",
                identifier=identifier,
                remaining=remaining,
            )
            return remaining
        except Exception as e:
            logger.error("rate_limit_remaining_error", error=str(e))
            return None

    async def reset_limits(self, identifier: str = "default") -> bool:
        try:
            key = f"{self._key_prefix}:{identifier}"
            await self._redis_session.delete(key)
            logger.info("rate_limit_reset", identifier=identifier, backend="redis")
            return True
        except Exception as e:
            logger.error("rate_limit_reset_error", error=str(e))
            return False
