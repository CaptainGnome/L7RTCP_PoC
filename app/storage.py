# l7rtcp_poc/app/storage.py
# Этот файл реализует простое in-memory хранилище для состояний передач (TransmissionState).

import asyncio
from typing import Dict, Optional
from .models import TransmissionState

class InMemoryTransmissionStorage:
    """
    Простое in-memory хранилище для состояний передач.
    Использует словарь для хранения и asyncio.Lock для обеспечения потокобезопасности.
    """

    def __init__(self):
        """
        Инициализирует хранилище.
        """
        # Словарь для хранения состояний передач.
        # Ключ: X-Transmission-ID, Значение: TransmissionState.
        self._store: Dict[str, TransmissionState] = {}
        # Асинхронная блокировка для предотвращения гонок данных
        # при одновременном доступе из разных запросов.
        self._lock = asyncio.Lock()

    async def create(self, transmission: TransmissionState) -> None:
        """
        Создает новую запись о передаче в хранилище.
        Если передача с таким ID уже существует, она будет перезаписана.
        """
        async with self._lock:
            # Простая реализация: перезаписываем существующую запись.
            # В более сложной логике можно проверять конфликты.
            self._store[transmission.id] = transmission

    async def get(self, transmission_id: str) -> Optional[TransmissionState]:
        """
        Получает состояние передачи по её ID.
        Возвращает TransmissionState или None, если передача не найдена.
        """
        async with self._lock:
            # Возвращаем копию или ссылку на объект.
            # В данном случае возвращаем ссылку.
            return self._store.get(transmission_id)

    async def update(self, transmission: TransmissionState) -> bool:
        """
        Обновляет существующую запись о передаче.
        Возвращает True, если запись была обновлена, False, если не найдена.
        """
        async with self._lock:
            if transmission.id in self._store:
                self._store[transmission.id] = transmission
                return True
            return False

    async def delete(self, transmission_id: str) -> bool:
        """
        Удаляет запись о передаче из хранилища.
        Возвращает True, если запись была удалена, False, если не найдена.
        """
        async with self._lock:
            if transmission_id in self._store:
                del self._store[transmission_id]
                return True
            return False

# Создаем глобальный экземпляр хранилища, который будет использоваться всем приложением.
storage = InMemoryTransmissionStorage()