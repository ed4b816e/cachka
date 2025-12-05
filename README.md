# 🌐 cachka

> **Enterprise-grade hybrid cache for Python**
> Flexible multi-layer caching with **memory (L1)**, **SQLite disk (L2)**, and **Redis (L3)** support.
> Works seamlessly in **async**, **sync**, and **threaded** environments.

[![PyPI - Version](https://img.shields.io/pypi/v/cachka.svg)](https://pypi.org/project/cachka)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/cachka)](https://pypi.org/project/cachka)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## ✨ Features

- **Flexible multi-layer architecture**: Compose cache layers (memory, SQLite, Redis) in any order
- **Async & sync support**: Use the same decorator everywhere, native sync/async implementations
- **TTL with smart LRU eviction** (no memory leaks)
- **Observability**: Prometheus metrics, OpenTelemetry tracing
- **Security**: AES-GCM encryption for SQLite storage
- **Resilience**: Circuit breaker, graceful degradation
- **Zero dependencies** for core functionality (SQLite included)
- **Type-safe**: Full type hints and dataclass configs
- **Redis support**: Optional Redis backend for distributed caching

---

## 🚀 Quick Start

### 1. Install

```bash
# Core (required) - includes memory and SQLite
pip install cachka

# With Prometheus metrics
pip install "cachka[prometheus]"

# With Redis support
pip install "cachka[redis]"

# Full enterprise features
pip install "cachka[full]"
```

### 2. Initialize Cache

```python
from cachka import cache_registry, CacheConfig
from cachka.sqlitecache import SQLiteCacheConfig
from cachka.ttllrucache import MemoryCacheConfig

# Basic initialization (memory + SQLite with defaults)
config = CacheConfig(
    cache_layers=[
        "memory",  # Default memory cache
        ("sqlite", SQLiteCacheConfig(db_path="cache.db"))  # SQLite with custom path
    ]
)
cache_registry.initialize(config)

# Advanced: Custom memory cache + SQLite
config = CacheConfig(
    cache_layers=[
        ("memory", MemoryCacheConfig(maxsize=2048, ttl=600)),
        ("sqlite", SQLiteCacheConfig(
            db_path="cache.db",
            enable_encryption=True,
            encryption_key="your-base64-encoded-32-byte-key"
        ))
    ],
    enable_metrics=True
)
cache_registry.initialize(config)

# With Redis (requires: pip install cachka[redis])
from cachka.rediscache import RedisCacheConfig

config = CacheConfig(
    cache_layers=[
        "memory",  # Fast L1
        ("sqlite", SQLiteCacheConfig(db_path="cache.db")),  # L2
        ("redis", RedisCacheConfig(host="localhost", port=6379))  # L3
    ]
)
cache_registry.initialize(config)
```

---

## 📖 Usage Examples

### Basic Async Function Caching

```python
import asyncio
from cachka import cached, cache_registry, CacheConfig
from cachka.sqlitecache import SQLiteCacheConfig

# Initialize cache
config = CacheConfig(
    cache_layers=[
        "memory",
        ("sqlite", SQLiteCacheConfig(db_path="cache.db"))
    ]
)
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
from cachka.sqlitecache import SQLiteCacheConfig

config = CacheConfig(
    cache_layers=[
        "memory",
        ("sqlite", SQLiteCacheConfig(db_path="cache.db"))
    ]
)
cache_registry.initialize(config)

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

### Class Methods with `simplified_self_serialization`

```python
from cachka import cached, cache_registry, CacheConfig
from cachka.sqlitecache import SQLiteCacheConfig

config = CacheConfig(
    cache_layers=[
        "memory",
        ("sqlite", SQLiteCacheConfig(db_path="cache.db"))
    ]
)
cache_registry.initialize(config)

class UserService:
    @cached(ttl=300, simplified_self_serialization=True)
    async def get_user(self, user_id: int):
        # Cache key will be based on user_id only, not self instance
        # Uses class name instead of self for cache key generation
        return await self._fetch_from_db(user_id)

    async def _fetch_from_db(self, user_id: int):
        # Database query simulation
        return {"id": user_id, "name": f"User {user_id}"}

service = UserService()
user = await service.get_user(123)  # Cached by user_id and class name only
```

### Multi-Layer Cache Configuration

```python
from cachka import cache_registry, CacheConfig
from cachka.ttllrucache import MemoryCacheConfig
from cachka.sqlitecache import SQLiteCacheConfig
from cachka.rediscache import RedisCacheConfig
import base64
import secrets

# Generate encryption key (32 bytes, base64-encoded)
encryption_key = base64.b64encode(secrets.token_bytes(32)).decode()

config = CacheConfig(
    cache_layers=[
        # L1: Fast in-memory cache
        ("memory", MemoryCacheConfig(
            maxsize=4096,
            ttl=1800,  # 30 minutes
            shards=8
        )),
        # L2: Persistent SQLite cache
        ("sqlite", SQLiteCacheConfig(
            db_path="secure_cache.db",
            enable_encryption=True,
            encryption_key=encryption_key
        )),
        # L3: Distributed Redis cache (optional)
        ("redis", RedisCacheConfig(
            host="localhost",
            port=6379,
            db=0,
            key_prefix="myapp:"
        ))
    ],
    vacuum_interval=3600,  # Cleanup every hour
    cleanup_on_start=True,  # Clean expired on startup
    enable_metrics=True,   # Prometheus metrics
    circuit_breaker_threshold=50,  # Open circuit after 50 failures
    circuit_breaker_window=60      # Recovery window: 60 seconds
)

cache_registry.initialize(config)
```

### Redis Cache (Optional)

```python
from cachka import cache_registry, CacheConfig
from cachka.rediscache import RedisCacheConfig

# Install: pip install cachka[redis]

config = CacheConfig(
    cache_layers=[
        "memory",  # Fast local cache
        ("redis", RedisCacheConfig(
            host="localhost",
            port=6379,
            db=0,
            password=None,  # Optional
            key_prefix="myapp:",  # Namespace for keys
            max_connections=50
        ))
    ]
)
cache_registry.initialize(config)

# Use as normal - Redis handles TTL automatically
@cached(ttl=300)
async def get_data(key: str):
    return {"data": f"value for {key}"}
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
#     "circuit_breaker": "CLOSED",
#     "cache_layers_count": 2
# }
```

---

## 🏗️ Architecture

### Cache Layers

cachka supports flexible multi-layer caching:

1. **Memory (L1)**: Fast in-memory LRU cache with TTL
   - Configurable via `MemoryCacheConfig`
   - Sharded for better concurrency
   - Automatic eviction when full

2. **SQLite (L2)**: Persistent disk-based cache
   - Configurable via `SQLiteCacheConfig`
   - Optional AES-GCM encryption
   - Automatic cleanup of expired entries

3. **Redis (L3)**: Distributed cache (optional)
   - Configurable via `RedisCacheConfig`
   - Requires: `pip install cachka[redis]`
   - Automatic TTL handling
   - Connection pooling

### Cache Flow

When you call `cache.get(key)`:

1. Checks L1 (memory) → if found, return
2. Checks L2 (SQLite) → if found, promote to L1 and return
3. Checks L3 (Redis) → if found, promote to L2 and L1, return
4. If not found in any layer → return None

When you call `cache.set(key, value, ttl)`:

1. Writes to all configured layers (write-through)
2. Each layer respects its own TTL configuration

---

## ⚙️ Configuration

### CacheConfig

Main configuration class:

```python
@dataclass
class CacheConfig:
    cache_layers: list[Union[str, tuple[str, Any]]]  # Required: list of cache layers
    vacuum_interval: Optional[int] = None  # SQLite vacuum interval (seconds)
    cleanup_on_start: bool = False  # Clean expired entries on startup
    enable_metrics: bool = False  # Enable Prometheus metrics
    name: str = "default_cache"  # Cache name for metrics
    circuit_breaker_threshold: int = 50  # Failures before opening circuit
    circuit_breaker_window: int = 60  # Recovery window (seconds)
```

### MemoryCacheConfig

```python
@dataclass
class MemoryCacheConfig:
    maxsize: int = 1024  # Maximum cache size
    ttl: int = 300  # Time to live (seconds)
    shards: int = 8  # Number of shards for concurrency
    enable_metrics: bool = False  # Enable metrics for this layer
    name: str = "memory_cache"  # Layer name
```

### SQLiteCacheConfig

```python
@dataclass
class SQLiteCacheConfig:
    db_path: str = "cache.db"  # Database file path
    enable_encryption: bool = False  # Enable AES-GCM encryption
    encryption_key: Optional[str] = None  # Base64-encoded 32-byte key
    max_key_length: int = 512  # Maximum key length
```

### RedisCacheConfig

```python
@dataclass
class RedisCacheConfig:
    host: str = "localhost"  # Redis host
    port: int = 6379  # Redis port
    db: int = 0  # Redis database number
    password: Optional[str] = None  # Redis password
    socket_timeout: Optional[float] = None  # Socket timeout
    socket_connect_timeout: Optional[float] = None  # Connection timeout
    max_connections: int = 50  # Connection pool size
    key_prefix: str = "cachka:"  # Prefix for all keys
```

---

## 🔧 Advanced Usage

### Custom Cache Layer Order

You can configure cache layers in any order:

```python
# Memory only
config = CacheConfig(cache_layers=["memory"])

# SQLite only
config = CacheConfig(cache_layers=[("sqlite", SQLiteCacheConfig())])

# Redis only (requires redis)
config = CacheConfig(cache_layers=[("redis", RedisCacheConfig())])

# Custom order: Redis -> Memory -> SQLite
config = CacheConfig(
    cache_layers=[
        ("redis", RedisCacheConfig()),
        "memory",
        ("sqlite", SQLiteCacheConfig())
    ]
)
```

### Direct Cache Access

```python
from cachka import cache_registry

cache = cache_registry.get()

# Async operations
await cache.set("key", "value", ttl=60)
value = await cache.get("key")
await cache.delete("key")

# Sync operations
cache.set_sync("key", "value", ttl=60)
value = cache.get_sync("key")
cache.delete_sync("key")
```

---

## 📦 Installation Options

```bash
# Core (memory + SQLite)
pip install cachka

# With Prometheus metrics
pip install "cachka[prometheus]"

# With OpenTelemetry tracing
pip install "cachka[tracing]"

# With encryption support
pip install "cachka[encryption]"

# With Redis support
pip install "cachka[redis]"

# All features
pip install "cachka[full]"
```

---

## 🧪 Testing

```bash
# Install dev dependencies
pip install "cachka[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=cachka --cov-report=html
```

---

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

---

## 📚 API Reference

### Decorator

- `@cached(ttl=300, simplified_self_serialization=False)` - Cache decorator

### Configuration

- `CacheConfig` - Main cache configuration
- `MemoryCacheConfig` - Memory cache configuration
- `SQLiteCacheConfig` - SQLite cache configuration
- `RedisCacheConfig` - Redis cache configuration (optional)

### Registry

- `cache_registry.initialize(config)` - Initialize cache
- `cache_registry.get()` - Get cache instance
- `cache_registry.shutdown()` - Shutdown cache
- `cache_registry.reset()` - Reset registry

### Cache Interface

- `cache.get(key)` - Get value (async)
- `cache.get_sync(key)` - Get value (sync)
- `cache.set(key, value, ttl)` - Set value (async)
- `cache.set_sync(key, value, ttl)` - Set value (sync)
- `cache.delete(key)` - Delete key (async)
- `cache.delete_sync(key)` - Delete key (sync)
- `cache.cleanup_expired()` - Clean expired entries (async)
- `cache.cleanup_expired_sync()` - Clean expired entries (sync)
- `cache.health_check()` - Health check (async)
- `cache.get_metrics_text()` - Get Prometheus metrics
