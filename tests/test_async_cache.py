async def test_async_cache():
    import inspect
    import asyncio
    from cachka import cached, cache_registry, CacheConfig

    config = CacheConfig(vacuum_interval=None, cleanup_on_start=False, db_path=":memory:")
    cache_registry.initialize(config)

    @cached(ttl=10)
    async def wait(time: float):
        await asyncio.sleep(time)
        return "Done!"

    assert inspect.iscoroutinefunction(wait)

    assert await wait(0.1) == "Done!" # уменьшите время для теста!

    @cached(ttl=10)
    async def wait(time: float):
        await asyncio.sleep(time)
        raise ValueError("Not cached")

    # Проверяем кэш - второй вызов должен вернуть закэшированное значение
    assert await wait(0.1) == "Done!" # должно быть из кэша

    @cached(ttl=10)
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    assert fib(3)

    await cache_registry.shutdown()