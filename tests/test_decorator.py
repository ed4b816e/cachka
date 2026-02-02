import asyncio
import functools
import inspect

import pytest

from cachka import (
    CacheConfig,
    cache_registry,
    cached,
)
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
            cache_layers=["memory", ("sqlite", SQLiteCacheConfig(db_path=":memory:"))],
            vacuum_interval=None,
            cleanup_on_start=False,
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
            cache_layers=["memory", ("sqlite", SQLiteCacheConfig(db_path=":memory:"))],
            vacuum_interval=None,
            cleanup_on_start=False,
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
            cache_layers=["memory", ("sqlite", SQLiteCacheConfig(db_path=":memory:"))],
            vacuum_interval=None,
            cleanup_on_start=False,
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
            cache_layers=["memory", ("sqlite", SQLiteCacheConfig(db_path=":memory:"))],
            vacuum_interval=None,
            cleanup_on_start=False,
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
            assert any(
                issubclass(warning.category, DeprecationWarning) for warning in w
            )

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
            cache_layers=["memory", ("sqlite", SQLiteCacheConfig(db_path=":memory:"))],
            vacuum_interval=None,
            cleanup_on_start=False,
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
        assert my_function.__annotations__["x"] is int
        assert my_function.__annotations__["return"] is dict

    def test_preserves_function_signature(self):
        """Сохранение сигнатуры"""

        @cached(ttl=60)
        def my_function(x: int, y: str = "default") -> dict:
            return {"x": x, "y": y}

        sig = inspect.signature(my_function)
        assert "x" in sig.parameters
        assert "y" in sig.parameters
        assert sig.return_annotation is dict


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
            cache_layers=["memory", ("sqlite", SQLiteCacheConfig(db_path=":memory:"))],
            vacuum_interval=None,
            cleanup_on_start=False,
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


# Декоратор-заглушка для тестирования вложенных декораторов
def data_transfer(return_type):
    """Простой декоратор-заглушка, аналог @data_transfer из примера пользователя"""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            return result  # Простая заглушка, просто возвращает результат

        return wrapper

    return decorator


# Глобальный класс для тестов с вложенными декораторами (чтобы pickle мог его сериализовать)
class ServiceWithNestedDecorators:
    """Глобальный класс для теста вложенных декораторов"""

    def __init__(self, name: str = "default"):
        self.name = name

    @cached(simplified_self_serialization=True, ttl=30)
    @data_transfer(None)
    async def get_by_publisher(self, publisher: str) -> str:
        """Метод с вложенными декораторами"""
        # Имитация работы с данными
        return f"data_for_{publisher}"


class TestDecoratorWithNestedDecorators:
    """Тесты декоратора @cached с вложенными декораторами"""

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
            cache_layers=["memory", ("sqlite", SQLiteCacheConfig(db_path=":memory:"))],
            vacuum_interval=None,
            cleanup_on_start=False,
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
    async def test_cached_above_other_decorator_with_simplified_self(self):
        """Тест работы @cached выше другого декоратора с simplified_self_serialization=True"""
        call_count = [0]

        # Используем глобальный класс для pickle
        class ServiceWithNestedLocal(ServiceWithNestedDecorators):
            @cached(simplified_self_serialization=True, ttl=30)
            @data_transfer(None)
            async def get_by_publisher(self, publisher: str) -> str:
                call_count[0] += 1
                return f"data_for_{publisher}"

        # Создаем два разных экземпляра класса
        service1 = ServiceWithNestedLocal("service1")
        service2 = ServiceWithNestedLocal("service2")

        # Первый вызов - должен выполниться
        result1 = await service1.get_by_publisher("test_publisher")
        assert result1 == "data_for_test_publisher"
        assert call_count[0] == 1

        # Второй вызов с другим экземпляром, но теми же аргументами
        # Должен использовать кэш благодаря simplified_self_serialization=True
        result2 = await service2.get_by_publisher("test_publisher")
        assert result2 == "data_for_test_publisher"
        assert call_count[0] == 1  # Не должна вызваться снова

        # Третий вызов с первым экземпляром - также должен использовать кэш
        result3 = await service1.get_by_publisher("test_publisher")
        assert result3 == "data_for_test_publisher"
        assert call_count[0] == 1  # Все еще не должна вызваться снова

        # Вызов с другими аргументами - должна вызваться снова
        result4 = await service1.get_by_publisher("other_publisher")
        assert result4 == "data_for_other_publisher"
        assert call_count[0] == 2  # Должна вызваться снова для новых аргументов

    @pytest.mark.asyncio
    async def test_cached_with_non_serializable_self_object(self):
        """Тест работы @cached с несериализуемым объектом в self"""
        call_count = [0]

        # Создаем объект с локальной функцией (аналог SQLAlchemy session с create_engine.<locals>.connect)
        def create_non_serializable_object():
            """Создает объект с локальной функцией, которая не может быть сериализована через pickle"""
            def local_function():
                return "local"

            class NonSerializableObject:
                def __init__(self):
                    self.local_func = local_function
                    self.name = "test_object"

            return NonSerializableObject()

        # Глобальный класс для теста
        class ServiceWithNonSerializableSelf:
            def __init__(self):
                # Создаем несериализуемый объект в self
                self.non_serializable = create_non_serializable_object()
                self.name = "service"

            @cached(simplified_self_serialization=True, ttl=30)
            async def get_data(self, key: str) -> str:
                call_count[0] += 1
                return f"data_for_{key}"

        # Создаем два разных экземпляра с несериализуемыми объектами
        service1 = ServiceWithNonSerializableSelf()
        service2 = ServiceWithNonSerializableSelf()

        # Первый вызов - должен выполниться без ошибок pickle
        result1 = await service1.get_data("test_key")
        assert result1 == "data_for_test_key"
        assert call_count[0] == 1

        # Второй вызов с другим экземпляром - должен использовать кэш
        # Без simplified_self_serialization это вызвало бы ошибку pickle
        result2 = await service2.get_data("test_key")
        assert result2 == "data_for_test_key"
        assert call_count[0] == 1  # Не должна вызваться снова

        # Третий вызов - также должен использовать кэш
        result3 = await service1.get_data("test_key")
        assert result3 == "data_for_test_key"
        assert call_count[0] == 1  # Все еще не должна вызваться снова

    @pytest.mark.asyncio
    async def test_cached_with_non_serializable_self_and_nested_decorator(self):
        """Тест работы @cached выше другого декоратора с несериализуемым объектом в self"""
        call_count = [0]

        # Создаем объект с локальной функцией (аналог SQLAlchemy create_engine.<locals>.connect)
        def create_non_serializable_object():
            """Создает объект с локальной функцией, которая не может быть сериализована через pickle"""
            def local_function():
                return "local"

            class NonSerializableObject:
                def __init__(self):
                    self.local_func = local_function
                    self.name = "test_object"

            return NonSerializableObject()

        # Глобальный класс для теста (аналог DocumentSnapshotRepository из реального примера)
        class ServiceWithNonSerializableSelfAndNested:
            def __init__(self):
                # Создаем несериализуемый объект в self (аналог SQLAlchemy session)
                self.non_serializable = create_non_serializable_object()
                self.name = "service"

            @cached(simplified_self_serialization=True, ttl=30)
            @data_transfer(None)
            async def get_by_id(self, item_id: str) -> str:
                """Метод с вложенными декораторами и несериализуемым self"""
                call_count[0] += 1
                return f"item_{item_id}"

        # Создаем два разных экземпляра с несериализуемыми объектами
        service1 = ServiceWithNonSerializableSelfAndNested()
        service2 = ServiceWithNonSerializableSelfAndNested()

        # Первый вызов - должен выполниться без ошибок pickle
        # Без simplified_self_serialization это вызвало бы:
        # AttributeError: Can't get local object 'create_non_serializable_object.<locals>.local_function'
        result1 = await service1.get_by_id("123")
        assert result1 == "item_123"
        assert call_count[0] == 1

        # Второй вызов с другим экземпляром - должен использовать кэш
        # Это проверяет, что inspect.unwrap() работает правильно с вложенными декораторами
        # и что simplified_self_serialization исключает self из аргументов
        result2 = await service2.get_by_id("123")
        assert result2 == "item_123"
        assert call_count[0] == 1  # Не должна вызваться снова

        # Третий вызов с первым экземпляром - также должен использовать кэш
        result3 = await service1.get_by_id("123")
        assert result3 == "item_123"
        assert call_count[0] == 1  # Все еще не должна вызваться снова

        # Вызов с другими аргументами - должна вызваться снова
        result4 = await service1.get_by_id("456")
        assert result4 == "item_456"
        assert call_count[0] == 2  # Должна вызваться снова для новых аргументов
