import hashlib
import pickle
from typing import Tuple, Callable, Any


def make_cache_key(func_name: str, args: Tuple, kwargs: dict) -> str:
    """Генерирует ключ кэша на основе имени функции, аргументов и kwargs."""
    key_data = (func_name, args, tuple(sorted(kwargs.items())))
    return hashlib.sha256(
        pickle.dumps(key_data, protocol=pickle.HIGHEST_PROTOCOL)
    ).hexdigest()


def prepare_cache_key(func: Callable, args: Tuple, kwargs: dict, ignore_self: bool = False) -> str:
    """
    Подготавливает ключ кэша для декорированной функции.
    
    Args:
        func: Декорируемая функция
        args: Аргументы функции
        kwargs: Именованные аргументы функции
        ignore_self: Если True, исключает self из аргументов и добавляет имя класса в идентификатор
    
    Returns:
        Хеш-ключ для кэша
    """
    # Определяем аргументы для ключа (исключаем self если ignore_self=True)
    key_args = args[1:] if ignore_self and args else args
    
    # Формируем идентификатор функции
    if ignore_self and args:
        # Если ignore_self=True, включаем имя класса в ключ
        class_name = args[0].__class__.__name__
        func_identifier = f"{class_name}.{func.__name__}"
    else:
        func_identifier = func.__name__
    
    return make_cache_key(func_identifier, key_args, kwargs)