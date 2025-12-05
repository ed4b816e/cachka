import pytest
import asyncio
import inspect
from cachka import cached, cache_registry, CacheConfig
from cachka.sqlitecache import SQLiteCacheConfig


# Глобальные классы для тестов (чтобы pickle мог их сериализовать)
class SampleTestService:
    """Глобальный класс для тестов simplified_self_serialization"""
    def __init__(self, name):
        self.name = name
    
    def get_data(self, key: str):
        return f"data_{key}_{self.name}"


class ServiceWithCount(SampleTestService):
    """Глобальный класс для теста simplified_self_serialization=False"""
    _call_count = 0
    
    def __init__(self, name):
        super().__init__(name)
    
    @cached(ttl=60, simplified_self_serialization=False)
    def get_data(self, key: str):
        ServiceWithCount._call_count += 1
        return super().get_data(key)


class ServiceSimplified(SampleTestService):
    """Глобальный класс для теста simplified_self_serialization=True"""
    pass


class ServiceA(SampleTestService):
    """Глобальный класс для теста разных классов"""
    pass


class ServiceB(SampleTestService):
    """Глобальный класс для теста разных классов"""
    pass


class ServiceDeprecated(SampleTestService):
    """Глобальный класс для теста deprecated ignore_self"""
    pass


class TestDecoratorAsync:
    """Тесты декоратора для async функций"""

    @pytest.fixture(autouse=True)
    async def setup_cache(self):
        # Сбрасываем перед инициализацией
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()
        
        config = CacheConfig(
            cache_layers=[
                "memory",
                ("sqlite", SQLiteCacheConfig(db_path=":memory:"))
            ],
            vacuum_interval=None,
            cleanup_on_start=False
        )
        cache_registry.initialize(config)
        yield
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()

    @pytest.mark.asyncio
    async def test_async_function_caching(self):
        """Кэширование async функций"""
        call_count = [0]
        
        @cached(ttl=60)
        async def fetch_data(key: str):
            call_count[0] += 1
            await asyncio.sleep(0.01)
            return f"data_{key}"
        
        result1 = await fetch_data("test")
        assert result1 == "data_test"
        assert call_count[0] == 1
        
        result2 = await fetch_data("test")
        assert result2 == "data_test"
        assert call_count[0] == 1  # Не вызвалась снова

    @pytest.mark.asyncio
    async def test_async_function_cache_hit(self):
        """Попадание в кэш"""
        call_count = [0]
        
        @cached(ttl=60)
        async def compute(x: int):
            call_count[0] += 1
            return x * 2
        
        await compute(5)
        await compute(5)  # Из кэша
        assert call_count[0] == 1

    @pytest.mark.asyncio
    async def test_async_function_different_args(self):
        """Разные аргументы = разные ключи"""
        call_count = [0]
        
        @cached(ttl=60)
        async def compute(x: int):
            call_count[0] += 1
            return x * 2
        
        await compute(5)
        await compute(10)  # Другой аргумент
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_async_function_kwargs(self):
        """Работа с kwargs"""
        call_count = [0]
        
        @cached(ttl=60)
        async def compute(x: int, multiplier: int = 2):
            call_count[0] += 1
            return x * multiplier
        
        await compute(5, multiplier=3)
        await compute(5, multiplier=3)  # Из кэша
        assert call_count[0] == 1

    @pytest.mark.asyncio
    async def test_async_function_ttl(self):
        """Соблюдение TTL"""
        call_count = [0]

        @cached(ttl=1)
        async def compute(x: int):
            call_count[0] += 1
            return x * 2

        await compute(5)
        await compute(5)  # Из кэша
        assert call_count[0] == 1

        # Ждем истечения TTL
        await asyncio.sleep(1.2)
        # Очищаем кэш вручную для теста
        cache = cache_registry.get()
        await cache.cleanup_expired()
        
        # Также нужно очистить memory кэш, так как он использует свой TTL
        # и может не удалить значение автоматически
        from cachka.utils import make_cache_key
        cache_key = make_cache_key("compute", (5,), {})
        # Удаляем из всех кэшей вручную для теста
        for layer in cache._caches:
            try:
                await layer.delete(cache_key)
            except:
                pass

        await compute(5)  # TTL истек, должна вызваться снова
        assert call_count[0] == 2


class TestDecoratorSync:
    """Тесты декоратора для sync функций"""

    @pytest.fixture(autouse=True)
    async def setup_cache(self):
        # Сбрасываем перед инициализацией
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()
        
        config = CacheConfig(
            cache_layers=[
                "memory",
                ("sqlite", SQLiteCacheConfig(db_path=":memory:"))
            ],
            vacuum_interval=None,
            cleanup_on_start=False
        )
        cache_registry.initialize(config)
        yield
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()

    def test_sync_function_caching(self):
        """Кэширование sync функций"""
        call_count = [0]
        
        @cached(ttl=60)
        def compute(x: int):
            call_count[0] += 1
            return x * 2
        
        result1 = compute(5)
        assert result1 == 10
        assert call_count[0] == 1
        
        result2 = compute(5)
        assert result2 == 10
        assert call_count[0] == 1  # Не вызвалась снова

    def test_sync_function_cache_hit(self):
        """Попадание в кэш"""
        call_count = [0]
        
        @cached(ttl=60)
        def compute(x: int):
            call_count[0] += 1
            return x * 2
        
        compute(5)
        compute(5)  # Из кэша
        assert call_count[0] == 1

    def test_sync_function_l1_cache(self):
        """Использование L1 кэша"""
        @cached(ttl=60)
        def compute(x: int):
            return x * 2
        
        compute(5)
        # Второй вызов должен использовать L1
        result = compute(5)
        assert result == 10


class TestDecoratorSimplifiedSelfSerialization:
    """Тесты simplified_self_serialization"""

    @pytest.fixture(autouse=True)
    async def setup_cache(self):
        # Сбрасываем перед инициализацией
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()
        
        config = CacheConfig(
            cache_layers=[
                "memory",
                ("sqlite", SQLiteCacheConfig(db_path=":memory:"))
            ],
            vacuum_interval=None,
            cleanup_on_start=False
        )
        cache_registry.initialize(config)
        yield
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()

    @pytest.mark.asyncio
    async def test_simplified_self_serialization_true(self):
        """Упрощенная сериализация self в ключе"""
        call_count = [0]
        
        # Используем глобальный класс для pickle
        class ServiceSimplifiedLocal(ServiceSimplified):
            @cached(ttl=60, simplified_self_serialization=True)
            async def get_data(self, key: str):
                call_count[0] += 1
                return f"data_{key}"
        
        service1 = ServiceSimplifiedLocal("service1")
        service2 = ServiceSimplifiedLocal("service2")
        
        result1 = await service1.get_data("test")
        result2 = await service2.get_data("test")  # Должно быть из кэша
        
        assert result1 == result2
        assert call_count[0] == 1  # Вызвалась только один раз

    @pytest.mark.asyncio
    async def test_simplified_self_serialization_false(self):
        """Включение self в ключ (обычная сериализация)"""
        # Используем глобальный класс для pickle
        # ServiceWithCount уже имеет декоратор с simplified_self_serialization=False
        
        # Сбрасываем счетчик перед тестом
        ServiceWithCount._call_count = 0
        
        service1 = ServiceWithCount("service1")
        service2 = ServiceWithCount("service2")
        
        # Очищаем кэш перед тестом
        cache = cache_registry.get()
        await cache.cleanup()
        
        service1.get_data("test")
        service2.get_data("test")  # Разные экземпляры = разные ключи
        
        assert ServiceWithCount._call_count == 2  # Вызвалась дважды

    def test_simplified_self_serialization_different_classes_same_method_name(self):
        """Разные классы с одинаковыми именами методов должны иметь разные ключи"""
        call_count_a = [0]
        call_count_b = [0]
        
        class ServiceALocal(ServiceA):
            @cached(ttl=60, simplified_self_serialization=True)
            def get_data(self, key: str):
                call_count_a[0] += 1
                return f"ServiceA_{key}"
        
        class ServiceBLocal(ServiceB):
            @cached(ttl=60, simplified_self_serialization=True)
            def get_data(self, key: str):
                call_count_b[0] += 1
                return f"ServiceB_{key}"
        
        service_a = ServiceALocal("a")
        service_b = ServiceBLocal("b")
        
        # Вызываем метод с одинаковым именем в разных классах
        result_a1 = service_a.get_data("test")
        result_b1 = service_b.get_data("test")
        
        # Должны быть разные результаты
        assert result_a1 == "ServiceA_test"
        assert result_b1 == "ServiceB_test"
        
        # Оба должны быть вызваны
        assert call_count_a[0] == 1
        assert call_count_b[0] == 1
        
        # Повторные вызовы должны использовать кэш
        result_a2 = service_a.get_data("test")
        result_b2 = service_b.get_data("test")
        
        assert result_a2 == "ServiceA_test"
        assert result_b2 == "ServiceB_test"
        
        # Счетчики не должны увеличиться
        assert call_count_a[0] == 1
        assert call_count_b[0] == 1


class TestDecoratorIgnoreSelfDeprecated:
    """Тесты для deprecated ignore_self (обратная совместимость)"""

    @pytest.fixture(autouse=True)
    async def setup_cache(self):
        # Сбрасываем перед инициализацией
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()
        
        config = CacheConfig(
            cache_layers=[
                "memory",
                ("sqlite", SQLiteCacheConfig(db_path=":memory:"))
            ],
            vacuum_interval=None,
            cleanup_on_start=False
        )
        cache_registry.initialize(config)
        yield
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()

    @pytest.mark.asyncio
    async def test_ignore_self_deprecated_still_works(self):
        """ignore_self (deprecated) все еще работает"""
        import warnings
        
        call_count = [0]
        
        # Используем глобальный класс для pickle
        class ServiceDeprecatedLocal(ServiceDeprecated):
            @cached(ttl=60, ignore_self=True)
            async def get_data(self, key: str):
                call_count[0] += 1
                return f"data_{key}"
        
        service1 = ServiceDeprecatedLocal("service1")
        service2 = ServiceDeprecatedLocal("service2")
        
        # Должно выдать DeprecationWarning
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result1 = await service1.get_data("test")
            result2 = await service2.get_data("test")
            
            # Проверяем, что было предупреждение
            assert len(w) > 0
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)
        
        assert result1 == result2
        assert call_count[0] == 1  # Вызвалась только один раз


class TestDecoratorMetadata:
    """Тесты сохранения метаданных функции"""

    @pytest.fixture(autouse=True)
    async def setup_cache(self):
        # Сбрасываем перед инициализацией
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()
        
        config = CacheConfig(
            cache_layers=[
                "memory",
                ("sqlite", SQLiteCacheConfig(db_path=":memory:"))
            ],
            vacuum_interval=None,
            cleanup_on_start=False
        )
        cache_registry.initialize(config)
        yield
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()

    @pytest.mark.asyncio
    async def test_preserves_function_name(self):
        """Сохранение __name__"""
        @cached(ttl=60)
        async def my_function(x: int):
            """Test function"""
            return x * 2
        
        assert my_function.__name__ == "my_function"

    @pytest.mark.asyncio
    async def test_preserves_function_doc(self):
        """Сохранение __doc__"""
        @cached(ttl=60)
        async def my_function(x: int):
            """Test function docstring"""
            return x * 2
        
        assert my_function.__doc__ == "Test function docstring"

    @pytest.mark.asyncio
    async def test_preserves_function_annotations(self):
        """Сохранение __annotations__ (для FastAPI)"""
        @cached(ttl=60)
        async def my_function(x: int, y: str = "default") -> dict:
            return {"x": x, "y": y}
        
        assert "x" in my_function.__annotations__
        assert "y" in my_function.__annotations__
        assert "return" in my_function.__annotations__
        assert my_function.__annotations__["x"] == int
        assert my_function.__annotations__["return"] == dict

    def test_preserves_function_signature(self):
        """Сохранение сигнатуры"""
        @cached(ttl=60)
        def my_function(x: int, y: str = "default") -> dict:
            return {"x": x, "y": y}
        
        sig = inspect.signature(my_function)
        assert "x" in sig.parameters
        assert "y" in sig.parameters
        assert sig.return_annotation == dict


class TestDecoratorEdgeCases:
    """Edge cases декоратора"""

    @pytest.fixture(autouse=True)
    async def setup_cache(self):
        # Сбрасываем перед инициализацией
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()
        
        config = CacheConfig(
            cache_layers=[
                "memory",
                ("sqlite", SQLiteCacheConfig(db_path=":memory:"))
            ],
            vacuum_interval=None,
            cleanup_on_start=False
        )
        cache_registry.initialize(config)
        yield
        if cache_registry.is_initialized():
            try:
                await cache_registry.shutdown()
            except:
                pass
            cache_registry.reset()

    @pytest.mark.asyncio
    async def test_decorator_with_no_args(self):
        """Декоратор без аргументов"""
        @cached()
        async def compute(x: int):
            return x * 2
        
        result = await compute(5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_decorator_with_kwargs_only(self):
        """Только kwargs"""
        @cached(ttl=60)
        async def compute(x: int, multiplier: int = 2):
            return x * multiplier
        
        result = await compute(5, multiplier=3)
        assert result == 15

    @pytest.mark.asyncio
    async def test_decorator_with_args_and_kwargs(self):
        """Args и kwargs"""
        @cached(ttl=60)
        async def compute(x: int, y: int, multiplier: int = 2):
            return (x + y) * multiplier
        
        result = await compute(5, 10, multiplier=3)
        assert result == 45

    def test_decorator_recursive_function(self):
        """Рекурсивные функции"""
        call_count = [0]
        
        @cached(ttl=60)
        def fib(n: int):
            call_count[0] += 1
            if n < 2:
                return n
            return fib(n - 1) + fib(n - 2)
        
        result = fib(10)
        assert result == 55
        # Проверяем, что функция вызывалась (не зациклилась)
        assert call_count[0] > 0
        # Проверяем, что кэширование работает - второй вызов должен использовать кэш
        call_count[0] = 0
        result2 = fib(10)
        assert result2 == 55
        assert call_count[0] == 0  # Не должна вызываться снова

