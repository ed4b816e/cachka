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