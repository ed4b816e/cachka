from cachka.utils import (
    make_cache_key,
    prepare_cache_key,
)

# === Test Classes (вынесены на уровень модуля для pickle) ===


class MyClass:
    """Тестовый класс для проверки simplified_self_serialization=False"""

    def my_method(self, x: int):
        return x * 2


class MyService:
    """Тестовый класс для проверки simplified_self_serialization=True"""

    def get_data(self, key: str):
        return f"data_{key}"


class ServiceA:
    """Тестовый класс A для проверки различий между классами"""

    def get_data(self, key: str):
        return f"ServiceA_{key}"


class ServiceB:
    """Тестовый класс B для проверки различий между классами"""

    def get_data(self, key: str):
        return f"ServiceB_{key}"


class MyServiceWithInit:
    """Тестовый класс с __init__ для проверки разных экземпляров"""

    def __init__(self, name: str):
        self.name = name

    def get_data(self, key: str):
        return f"data_{key}"


class MyServiceProcess:
    """Тестовый класс для проверки process метода"""

    def process(self, x: int, y: int):
        return x + y


class MyServiceCompute:
    """Тестовый класс для проверки compute метода"""

    def compute(self, x: int, multiplier: int = 2):
        return x * multiplier


class MyServiceGetValue:
    """Тестовый класс для проверки get_value метода"""

    def get_value(self):
        return 42


class ServiceAForDifferent:
    """Тестовый класс A для проверки различий между классами (второй набор)"""

    def get_data(self, key: str):
        return f"A_{key}"


class ServiceBForDifferent:
    """Тестовый класс B для проверки различий между классами (второй набор)"""

    def get_data(self, key: str):
        return f"B_{key}"


class MyServiceForDeprecated:
    """Тестовый класс для проверки deprecated ignore_self"""

    def get_data(self, key: str):
        return f"data_{key}"


class TestMakeCacheKey:
    """Тесты генерации ключей кэша"""

    def test_key_generation_deterministic(self):
        """Ключ должен быть детерминированным"""
        key1 = make_cache_key("func", (1, 2), {"a": 3})
        key2 = make_cache_key("func", (1, 2), {"a": 3})
        assert key1 == key2

    def test_key_different_for_different_args(self):
        """Разные аргументы = разные ключи"""
        key1 = make_cache_key("func", (1,), {})
        key2 = make_cache_key("func", (2,), {})
        assert key1 != key2

    def test_key_same_for_same_args(self):
        """Одинаковые аргументы = одинаковый ключ"""
        key1 = make_cache_key("func", (1, 2, 3), {"x": 10, "y": 20})
        key2 = make_cache_key("func", (1, 2, 3), {"x": 10, "y": 20})
        assert key1 == key2

    def test_key_handles_kwargs_order(self):
        """Порядок kwargs не важен"""
        key1 = make_cache_key("func", (), {"a": 1, "b": 2})
        key2 = make_cache_key("func", (), {"b": 2, "a": 1})
        assert key1 == key2  # sorted(kwargs.items()) делает порядок неважным

    def test_key_different_functions(self):
        """Разные функции = разные ключи"""
        key1 = make_cache_key("func1", (1,), {})
        key2 = make_cache_key("func2", (1,), {})
        assert key1 != key2

    def test_key_with_none(self):
        """Ключ с None значениями"""
        key1 = make_cache_key("func", (None,), {"x": None})
        key2 = make_cache_key("func", (None,), {"x": None})
        assert key1 == key2

    def test_key_with_complex_objects(self):
        """Сложные объекты в аргументах"""
        obj1 = {"nested": [1, 2, 3]}
        obj2 = {"nested": [1, 2, 3]}
        key1 = make_cache_key("func", (obj1,), {})
        key2 = make_cache_key("func", (obj2,), {})
        assert key1 == key2

    def test_key_with_unicode(self):
        """Unicode в аргументах"""
        key1 = make_cache_key("func", ("тест",), {"ключ": "значение"})
        key2 = make_cache_key("func", ("тест",), {"ключ": "значение"})
        assert key1 == key2

    def test_key_length(self):
        """Длина ключа (SHA256 = 64 hex chars)"""
        key = make_cache_key("func", (1, 2, 3), {"a": "b"})
        assert len(key) == 64  # SHA256 hex digest length
        assert all(c in "0123456789abcdef" for c in key)

    def test_key_empty_args(self):
        """Пустые аргументы"""
        key1 = make_cache_key("func", (), {})
        key2 = make_cache_key("func", (), {})
        assert key1 == key2

    def test_key_only_kwargs(self):
        """Только kwargs"""
        key1 = make_cache_key("func", (), {"x": 1, "y": 2})
        key2 = make_cache_key("func", (), {"y": 2, "x": 1})
        assert key1 == key2

    def test_key_only_args(self):
        """Только args"""
        key1 = make_cache_key("func", (1, 2, 3), {})
        key2 = make_cache_key("func", (1, 2, 3), {})
        assert key1 == key2


class TestPrepareCacheKey:
    """Тесты функции prepare_cache_key"""

    def test_prepare_key_without_simplified_serialization(self):
        """Ключ без simplified_self_serialization"""

        def my_function(x: int, y: int):
            return x + y

        key1 = prepare_cache_key(my_function, (1, 2), {})
        key2 = prepare_cache_key(my_function, (1, 2), {})
        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex digest

    def test_prepare_key_with_simplified_self_serialization_false(self):
        """Ключ с simplified_self_serialization=False"""
        obj = MyClass()
        key1 = prepare_cache_key(
            MyClass.my_method, (obj, 5), {}, simplified_self_serialization=False
        )
        key2 = prepare_cache_key(
            MyClass.my_method, (obj, 5), {}, simplified_self_serialization=False
        )
        assert key1 == key2

    def test_prepare_key_with_simplified_self_serialization_true(self):
        """Ключ с simplified_self_serialization=True - исключает self и добавляет имя класса"""
        service1 = MyService()
        service2 = MyService()

        # С simplified_self_serialization=True ключи должны быть одинаковыми для разных экземпляров
        key1 = prepare_cache_key(
            MyService.get_data,
            (service1, "test"),
            {},
            simplified_self_serialization=True,
        )
        key2 = prepare_cache_key(
            MyService.get_data,
            (service2, "test"),
            {},
            simplified_self_serialization=True,
        )
        assert key1 == key2  # Одинаковые ключи для разных экземпляров

    def test_prepare_key_simplified_self_serialization_includes_class_name(self):
        """При simplified_self_serialization=True имя класса включается в ключ"""
        service_a = ServiceA()
        service_b = ServiceB()

        # Разные классы с одинаковыми именами методов должны иметь разные ключи
        key_a = prepare_cache_key(
            ServiceA.get_data,
            (service_a, "test"),
            {},
            simplified_self_serialization=True,
        )
        key_b = prepare_cache_key(
            ServiceB.get_data,
            (service_b, "test"),
            {},
            simplified_self_serialization=True,
        )
        assert key_a != key_b  # Разные ключи для разных классов

    def test_prepare_key_simplified_self_serialization_excludes_self_from_args(self):
        """При simplified_self_serialization=True self исключается из аргументов"""
        service = MyServiceProcess()

        # С simplified_self_serialization=True self не должен влиять на ключ
        key1 = prepare_cache_key(
            MyServiceProcess.process,
            (service, 1, 2),
            {},
            simplified_self_serialization=True,
        )
        key2 = prepare_cache_key(
            MyServiceProcess.process,
            (service, 1, 2),
            {},
            simplified_self_serialization=True,
        )
        assert key1 == key2

        # Ключ должен зависеть только от аргументов после self
        key3 = prepare_cache_key(
            MyServiceProcess.process,
            (service, 1, 3),
            {},
            simplified_self_serialization=True,
        )
        assert key1 != key3  # Разные аргументы = разные ключи

    def test_prepare_key_simplified_self_serialization_with_kwargs(self):
        """simplified_self_serialization=True с kwargs"""
        service = MyServiceCompute()
        key1 = prepare_cache_key(
            MyServiceCompute.compute,
            (service, 5),
            {"multiplier": 3},
            simplified_self_serialization=True,
        )
        key2 = prepare_cache_key(
            MyServiceCompute.compute,
            (service, 5),
            {"multiplier": 3},
            simplified_self_serialization=True,
        )
        assert key1 == key2

    def test_prepare_key_simplified_self_serialization_no_args(self):
        """simplified_self_serialization=True без аргументов (кроме self)"""
        service = MyServiceGetValue()
        key1 = prepare_cache_key(
            MyServiceGetValue.get_value,
            (service,),
            {},
            simplified_self_serialization=True,
        )
        key2 = prepare_cache_key(
            MyServiceGetValue.get_value,
            (service,),
            {},
            simplified_self_serialization=True,
        )
        assert key1 == key2

    def test_prepare_key_simplified_self_serialization_empty_args(self):
        """simplified_self_serialization=True с пустыми args (нет self)"""

        def standalone_function(x: int):
            return x * 2

        # Если нет args или это не метод класса, simplified_self_serialization не должен влиять
        key1 = prepare_cache_key(
            standalone_function, (), {}, simplified_self_serialization=True
        )
        key2 = prepare_cache_key(
            standalone_function, (5,), {}, simplified_self_serialization=False
        )
        # Разные аргументы, но проверяем что функция работает
        assert len(key1) == 64
        assert len(key2) == 64

    def test_prepare_key_different_instances_same_class_simplified_serialization(self):
        """Разные экземпляры одного класса с simplified_self_serialization=True дают одинаковые ключи"""
        service1 = MyServiceWithInit("service1")
        service2 = MyServiceWithInit("service2")

        # Разные экземпляры, но simplified_self_serialization=True - ключи должны быть одинаковыми
        key1 = prepare_cache_key(
            MyServiceWithInit.get_data,
            (service1, "test"),
            {},
            simplified_self_serialization=True,
        )
        key2 = prepare_cache_key(
            MyServiceWithInit.get_data,
            (service2, "test"),
            {},
            simplified_self_serialization=True,
        )
        assert key1 == key2

    def test_prepare_key_different_instances_different_class_simplified_serialization(
        self,
    ):
        """Разные классы с simplified_self_serialization=True дают разные ключи"""
        service_a = ServiceAForDifferent()
        service_b = ServiceBForDifferent()

        key_a = prepare_cache_key(
            ServiceAForDifferent.get_data,
            (service_a, "test"),
            {},
            simplified_self_serialization=True,
        )
        key_b = prepare_cache_key(
            ServiceBForDifferent.get_data,
            (service_b, "test"),
            {},
            simplified_self_serialization=True,
        )
        assert key_a != key_b  # Разные классы = разные ключи

    # Тесты для обратной совместимости с ignore_self (deprecated)
    def test_prepare_key_ignore_self_deprecated_still_works(self):
        """ignore_self (deprecated) все еще работает"""
        import warnings

        service1 = MyServiceForDeprecated()
        service2 = MyServiceForDeprecated()

        # Должно выдать DeprecationWarning, но работать
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            key1 = prepare_cache_key(
                MyServiceForDeprecated.get_data,
                (service1, "test"),
                {},
                ignore_self=True,
            )
            key2 = prepare_cache_key(
                MyServiceForDeprecated.get_data,
                (service2, "test"),
                {},
                ignore_self=True,
            )

            # Проверяем, что было предупреждение
            assert len(w) > 0
            assert any(
                issubclass(warning.category, DeprecationWarning) for warning in w
            )

        assert key1 == key2  # Одинаковые ключи для разных экземпляров
