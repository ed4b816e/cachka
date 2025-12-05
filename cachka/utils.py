import hashlib
import pickle
import inspect
import warnings
from typing import Tuple, Callable


def make_cache_key(func_name: str, args: Tuple, kwargs: dict) -> str:
    """Генерирует ключ кэша на основе имени функции, аргументов и kwargs."""
    key_data = (func_name, args, tuple(sorted(kwargs.items())))
    return hashlib.sha256(
        pickle.dumps(key_data, protocol=pickle.HIGHEST_PROTOCOL)
    ).hexdigest()


def _is_class_method(func: Callable, args: Tuple) -> bool:
    """
    Проверяет, является ли функция методом класса (bound method).
    
    Проверяет, что первый аргумент является экземпляром класса,
    который содержит метод с именем функции.
    
    Args:
        func: Функция для проверки
        args: Аргументы функции
    
    Returns:
        True если это метод класса, False иначе
    """
    if not args:
        return False
    
    first_arg = args[0]
    
    # Проверяем, что первый аргумент является экземпляром класса
    if not hasattr(first_arg, '__class__'):
        return False
    
    # Получаем имя функции (может быть обернуто декоратором)
    func_name = getattr(func, '__name__', None)
    if not func_name:
        return False
    
    # Получаем класс первого аргумента
    instance_class = first_arg.__class__
    
    # Проверяем, есть ли метод с таким именем в классе или его родителях
    # Используем getmro для проверки всей иерархии наследования
    for cls in inspect.getmro(instance_class):
        if hasattr(cls, func_name):
            # Проверяем, что это действительно метод или функция (не просто атрибут)
            attr = getattr(cls, func_name)
            if inspect.ismethod(attr) or inspect.isfunction(attr):
                # Если метод с таким именем существует в классе, это метод класса
                # Не проверяем точное совпадение функции, так как она может быть обернута декоратором
                return True
    
    return False


def prepare_cache_key(
    func: Callable, 
    args: Tuple, 
    kwargs: dict, 
    ignore_self: bool = False,
    simplified_self_serialization: bool = False
) -> str:
    """
    Подготавливает ключ кэша для декорированной функции.
    
    Args:
        func: Декорируемая функция
        args: Аргументы функции
        kwargs: Именованные аргументы функции
        ignore_self: [DEPRECATED] Используйте simplified_self_serialization вместо этого.
                     Если True, исключает self из аргументов и добавляет имя класса в идентификатор.
        simplified_self_serialization: Если True, использует упрощенную сериализацию self:
                                       исключает self из аргументов и использует имя класса вместо него.
                                       Полезно для методов, где self плохо сериализуется.
                                       Применяется только если функция является методом класса (определяется автоматически).
    
    Returns:
        Хеш-ключ для кэша
    """
    # Deprecation warning для ignore_self
    if ignore_self:
        warnings.warn(
            "Параметр 'ignore_self' устарел. Используйте 'simplified_self_serialization' вместо этого.",
            DeprecationWarning,
            stacklevel=2
        )
    
    # Определяем, нужно ли использовать упрощенную сериализацию self
    use_simplified_serialization = simplified_self_serialization or ignore_self
    
    # Автоматически определяем, является ли функция методом класса
    is_method = _is_class_method(func, args)
    
    # Если это метод класса и включена упрощенная сериализация
    if use_simplified_serialization and is_method and args:
        # Исключаем self из аргументов
        key_args = args[1:]
        # Включаем имя класса в идентификатор функции
        class_name = args[0].__class__.__name__
        func_identifier = f"{class_name}.{func.__name__}"
    else:
        # Используем все аргументы
        key_args = args
        func_identifier = func.__name__
    
    return make_cache_key(func_identifier, key_args, kwargs)