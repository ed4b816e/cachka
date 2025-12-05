"""
Интерфейс для всех реализаций кэшей.
"""

from abc import (
    ABC,
    abstractmethod,
)
from typing import (
    Any,
    Optional,
)


class ICache(ABC):
    """
    Общий интерфейс для всех реализаций кэшей.

    Поддерживает как синхронные, так и асинхронные операции.
    Реализации могут поддерживать только sync или только async методы,
    или оба варианта.

    Этот интерфейс позволяет создавать композитные кэши из нескольких слоев (L1, L2, ..., LN).
    """

    # === Async API ===

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Асинхронное получение значения из кэша"""
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Асинхронная установка значения в кэш"""
        ...

    # === Sync API ===

    def get_sync(self, key: str) -> Optional[Any]:
        """
        Синхронное получение значения из кэша.

        По умолчанию выбрасывает NotImplementedError.
        Реализации должны переопределить этот метод для поддержки sync API.
        """
        raise NotImplementedError("Sync API not supported by this cache implementation")

    def set_sync(self, key: str, value: Any, ttl: int) -> None:
        """
        Синхронная установка значения в кэш.

        По умолчанию выбрасывает NotImplementedError.
        Реализации должны переопределить этот метод для поддержки sync API.
        """
        raise NotImplementedError("Sync API not supported by this cache implementation")

    # === Optional methods ===

    async def delete(self, key: str) -> None:
        """Удаление ключа из кэша (опционально)"""
        raise NotImplementedError("Delete not supported by this cache implementation")

    def delete_sync(self, key: str) -> None:
        """Синхронное удаление ключа из кэша (опционально)"""
        raise NotImplementedError("Delete not supported by this cache implementation")

    async def cleanup_expired(self) -> int:
        """Очистка истекших записей (опционально)"""
        raise NotImplementedError("Cleanup not supported by this cache implementation")

    def cleanup_expired_sync(self) -> int:
        """Синхронная очистка истекших записей (опционально)"""
        raise NotImplementedError("Cleanup not supported by this cache implementation")

    async def close(self) -> None:
        """Закрытие кэша и освобождение ресурсов (опционально)"""
        pass

    def close_sync(self) -> None:
        """Синхронное закрытие кэша и освобождение ресурсов (опционально)"""
        pass
