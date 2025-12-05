# 🌐 cachka

> **Enterprise-grade hybrid cache for Python**
> Combines **in-memory (L1)** and **disk-based (L2)** caching with observability, encryption, and circuit breaking.
> Works seamlessly in **async**, **sync**, and **threaded** environments.

[![PyPI - Version](https://img.shields.io/pypi/v/cachka.svg)](https://pypi.org/project/cachka)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/cachka)](https://pypi.org/project/cachka)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## ✨ Features

- **Hybrid architecture**: L1 (memory) + L2 (SQLite disk)
- **Async & sync support**: Use the same decorator everywhere
- **TTL with smart LRU eviction** (no memory leaks)
- **Observability**: Prometheus metrics, OpenTelemetry tracing
- **Security**: AES-GCM encryption for disk storage
- **Resilience**: Circuit breaker, graceful degradation
- **Zero dependencies** for core functionality
- **Type-safe**: Full type hints and Pydantic config

---

## 🚀 Quick Start

### 1. Install

```bash
# Core (required)
pip install cachka

# With Prometheus metrics
pip install "cachka[prometheus]"

# Full enterprise features
pip install "cachka[full]"
```

### 2. Initialize Cache

```python
from cachka import cache_registry, CacheConfig

# Basic initialization
cache_registry.initialize()

# Or with custom configuration
config = CacheConfig(
    db_path="my_cache.db",
    l1_maxsize=2048,  # L1 cache size
    l1_ttl=600,       # L1 TTL in seconds
    enable_metrics=True,
    enable_encryption=True,
    encryption_key="your-base64-encoded-32-byte-key"
)
cache_registry.initialize(config)
```

---

## 📖 Usage Examples

### Basic Async Function Caching

```python
import asyncio
from cachka import cached, cache_registry, CacheConfig

# Initialize cache
config = CacheConfig(db_path="cache.db")
cache_registry.initialize(config)

@cached(ttl=300)  # Cache for 5 minutes
async def fetch_user_data(user_id: int):
    # Simulate API call
    await asyncio.sleep(0.1)
    return {"id": user_id, "name": f"User {user_id}"}

async def main():
    # First call - fetches data
    user1 = await fetch_user_data(1)
    print(user1)  # {"id": 1, "name": "User 1"}

    # Second call - returns cached data (no API call)
    user1_cached = await fetch_user_data(1)
    print(user1_cached)  # {"id": 1, "name": "User 1"} (from cache)

    # Cleanup
    await cache_registry.shutdown()

asyncio.run(main())
```

### Sync Function Caching

```python
from cachka import cached, cache_registry, CacheConfig

cache_registry.initialize()

@cached(ttl=60)
def expensive_computation(n: int) -> int:
    """Fibonacci calculation - cached after first call"""
    if n < 2:
        return n
    return expensive_computation(n - 1) + expensive_computation(n - 2)

# First call - computes
result1 = expensive_computation(30)  # Takes time

# Second call - returns cached result instantly
result2 = expensive_computation(30)  # Instant!
```

### Class Methods with `ignore_self`

```python
from cachka import cached, cache_registry, CacheConfig

cache_registry.initialize()

class UserService:
    @cached(ttl=300, ignore_self=True)
    async def get_user(self, user_id: int):
        # Cache key will be based on user_id only, not self instance
        return await self._fetch_from_db(user_id)

    async def _fetch_from_db(self, user_id: int):
        # Database query simulation
        return {"id": user_id, "name": f"User {user_id}"}

service = UserService()
user = await service.get_user(123)  # Cached by user_id only
```

### Advanced Configuration

```python
from cachka import cache_registry, CacheConfig
import base64
import secrets

# Generate encryption key (32 bytes, base64-encoded)
encryption_key = base64.b64encode(secrets.token_bytes(32)).decode()

config = CacheConfig(
    db_path="secure_cache.db",
    name="my_cache",
    l1_maxsize=4096,              # Larger L1 cache
    l1_ttl=1800,                   # 30 minutes L1 TTL
    vacuum_interval=3600,          # Cleanup every hour
    cleanup_on_start=True,          # Clean expired on startup
    enable_metrics=True,            # Prometheus metrics
    enable_encryption=True,         # AES-GCM encryption
    encryption_key=encryption_key,  # Your encryption key
    circuit_breaker_threshold=50,   # Open circuit after 50 failures
    circuit_breaker_window=60       # Recovery window: 60 seconds
)

cache_registry.initialize(config)
```

### Graceful Shutdown

```python
import asyncio
from cachka import cache_registry

async def main():
    # Your application code
    pass

# Cleanup on application exit
async def cleanup():
    await cache_registry.shutdown()

# In FastAPI, for example:
# @app.on_event("shutdown")
# async def shutdown_event():
#     await cache_registry.shutdown()
```

### Accessing Metrics (Prometheus)

```python
from cachka import cache_registry

# After enabling metrics in config
cache = cache_registry.get()
metrics_text = cache.get_metrics_text()
print(metrics_text)
# Output: Prometheus metrics in text format
```

### Health Check

```python
from cachka import cache_registry

cache = cache_registry.get()
health = await cache.health_check()
print(health)
# {
#     "status": "healthy",
#     "l1_size": 42,
#     "circuit_breaker": "CLOSED",
#     "storage": "ok"
# }
```
