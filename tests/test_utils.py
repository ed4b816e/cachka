import pytest
from cachka.utils import make_cache_key, prepare_cache_key


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
        assert all(c in '0123456789abcdef' for c in key)

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

    def test_prepare_key_without_ignore_self(self):
        """Ключ без ignore_self"""
        def my_function(x: int, y: int):
            return x + y
        
        key1 = prepare_cache_key(my_function, (1, 2), {})
        key2 = prepare_cache_key(my_function, (1, 2), {})
        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex digest

    def test_prepare_key_with_ignore_self_false(self):
        """Ключ с ignore_self=False"""
        class MyClass:
            def my_method(self, x: int):
                return x * 2
        
        obj = MyClass()
        key1 = prepare_cache_key(MyClass.my_method, (obj, 5), {}, ignore_self=False)
        key2 = prepare_cache_key(MyClass.my_method, (obj, 5), {}, ignore_self=False)
        assert key1 == key2

    def test_prepare_key_with_ignore_self_true(self):
        """Ключ с ignore_self=True - исключает self и добавляет имя класса"""
        class MyService:
            def get_data(self, key: str):
                return f"data_{key}"
        
        service1 = MyService()
        service2 = MyService()
        
        # С ignore_self=True ключи должны быть одинаковыми для разных экземпляров
        key1 = prepare_cache_key(MyService.get_data, (service1, "test"), {}, ignore_self=True)
        key2 = prepare_cache_key(MyService.get_data, (service2, "test"), {}, ignore_self=True)
        assert key1 == key2  # Одинаковые ключи для разных экземпляров

    def test_prepare_key_ignore_self_includes_class_name(self):
        """При ignore_self=True имя класса включается в ключ"""
        class ServiceA:
            def get_data(self, key: str):
                return f"ServiceA_{key}"
        
        class ServiceB:
            def get_data(self, key: str):
                return f"ServiceB_{key}"
        
        service_a = ServiceA()
        service_b = ServiceB()
        
        # Разные классы с одинаковыми именами методов должны иметь разные ключи
        key_a = prepare_cache_key(ServiceA.get_data, (service_a, "test"), {}, ignore_self=True)
        key_b = prepare_cache_key(ServiceB.get_data, (service_b, "test"), {}, ignore_self=True)
        assert key_a != key_b  # Разные ключи для разных классов

    def test_prepare_key_ignore_self_excludes_self_from_args(self):
        """При ignore_self=True self исключается из аргументов"""
        class MyService:
            def process(self, x: int, y: int):
                return x + y
        
        service = MyService()
        
        # С ignore_self=True self не должен влиять на ключ
        key1 = prepare_cache_key(MyService.process, (service, 1, 2), {}, ignore_self=True)
        key2 = prepare_cache_key(MyService.process, (service, 1, 2), {}, ignore_self=True)
        assert key1 == key2
        
        # Ключ должен зависеть только от аргументов после self
        key3 = prepare_cache_key(MyService.process, (service, 1, 3), {}, ignore_self=True)
        assert key1 != key3  # Разные аргументы = разные ключи

    def test_prepare_key_ignore_self_with_kwargs(self):
        """ignore_self=True с kwargs"""
        class MyService:
            def compute(self, x: int, multiplier: int = 2):
                return x * multiplier
        
        service = MyService()
        key1 = prepare_cache_key(MyService.compute, (service, 5), {"multiplier": 3}, ignore_self=True)
        key2 = prepare_cache_key(MyService.compute, (service, 5), {"multiplier": 3}, ignore_self=True)
        assert key1 == key2

    def test_prepare_key_ignore_self_no_args(self):
        """ignore_self=True без аргументов (кроме self)"""
        class MyService:
            def get_value(self):
                return 42
        
        service = MyService()
        key1 = prepare_cache_key(MyService.get_value, (service,), {}, ignore_self=True)
        key2 = prepare_cache_key(MyService.get_value, (service,), {}, ignore_self=True)
        assert key1 == key2

    def test_prepare_key_ignore_self_empty_args(self):
        """ignore_self=True с пустыми args (нет self)"""
        def standalone_function(x: int):
            return x * 2
        
        # Если нет args, ignore_self не должен влиять
        key1 = prepare_cache_key(standalone_function, (), {}, ignore_self=True)
        key2 = prepare_cache_key(standalone_function, (5,), {}, ignore_self=False)
        # Разные аргументы, но проверяем что функция работает
        assert len(key1) == 64
        assert len(key2) == 64

    def test_prepare_key_different_instances_same_class_ignore_self(self):
        """Разные экземпляры одного класса с ignore_self=True дают одинаковые ключи"""
        class MyService:
            def __init__(self, name: str):
                self.name = name
            
            def get_data(self, key: str):
                return f"data_{key}"
        
        service1 = MyService("service1")
        service2 = MyService("service2")
        
        # Разные экземпляры, но ignore_self=True - ключи должны быть одинаковыми
        key1 = prepare_cache_key(MyService.get_data, (service1, "test"), {}, ignore_self=True)
        key2 = prepare_cache_key(MyService.get_data, (service2, "test"), {}, ignore_self=True)
        assert key1 == key2

    def test_prepare_key_different_instances_different_class_ignore_self(self):
        """Разные классы с ignore_self=True дают разные ключи"""
        class ServiceA:
            def get_data(self, key: str):
                return f"A_{key}"
        
        class ServiceB:
            def get_data(self, key: str):
                return f"B_{key}"
        
        service_a = ServiceA()
        service_b = ServiceB()
        
        key_a = prepare_cache_key(ServiceA.get_data, (service_a, "test"), {}, ignore_self=True)
        key_b = prepare_cache_key(ServiceB.get_data, (service_b, "test"), {}, ignore_self=True)
        assert key_a != key_b  # Разные классы = разные ключи

