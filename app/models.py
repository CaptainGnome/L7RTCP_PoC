# l7rtcp_poc/app/models.py
# Этот файл определяет основные структуры данных для L7RTCP PoC.

from pydantic import BaseModel, Field
from enum import Enum
from typing import List, Dict, Optional, Set
import time # Для работы с временными метками

# --- Определение Feature Toggles ---

class FeatureToggle(str, Enum):
    """
    Перечисление доступных фич протокола.
    Используется для согласования возможностей между клиентом и сервером.
    """
    CORE = "core" # Всегда включена неявно
    RESEND = "resend" # Возобновление после прерываний
    TTL = "ttl" # Контроль времени жизни сессии
    BACKPRESSURE = "backpressure" # Обратная связь по нагрузке
    MULTISTREAM = "multistream" # Мультиплексирование потоков
    PULL = "pull" # Режим получения чанков по запросу
    PAUSE = "pause" # Пауза/возобновление потоков
    STATELESS = "stateless" # Работа без сохранения состояния на сервере
    FEC = "fec" # Коды исправления ошибок
    METRICS = "metrics" # Метрики для мониторинга

# --- Структуры данных для хендшейка ---

class StreamInfo(BaseModel):
    """
    Представляет информацию о потоке, передаваемую в заголовках.
    Например: video;res=480 или audio;lang=en.
    """
    # ID потока, включая суб-теги.
    id: str

# --- Внутренние структуры данных сервера ---

class StreamState(BaseModel):
    """
    Внутреннее состояние одного логического потока внутри передачи.
    Хранит информацию о полученных чанках.
    В PoC "полученные" чанки = "отправленные" чанки.
    """
    # Идентификатор потока (например, "video;res=480").
    id: str
    # Множество ID отправленных чанков. Используем множество для быстрого поиска.
    # TODO: В реальном сервере нужно разделить "отправленные" и "подтверждённые получения"
    received_chunks: Set[int] = Field(default_factory=set)
    # Общее количество чанков в потоке (если известно).
    total_chunks: Optional[int] = None

class TransmissionState(BaseModel):
    """
    Внутреннее состояние одной сессии передачи данных.
    Это основная структура, которую сервер хранит в памяти.
    """
    # Уникальный идентификатор передачи (X-Transmission-ID).
    id: str
    # Идентификатор клиента (X-Client-ID).
    client_id: str
    # Словарь состояний потоков. Ключ - ID потока, значение - StreamState.
    streams: Dict[str, StreamState] = Field(default_factory=dict)
    # Список фич, согласованных и включенных для этой сессии.
    features_enabled: List[FeatureToggle]
    # Время жизни сессии в секундах (если согласовано).
    ttl_seconds: Optional[int] = None
    # Временная метка создания сессии (timestamp).
    created_at: float
    # Временная метка последнего получения данных (timestamp).
    # В PoC это также время последней "отправки".
    last_received_time: float
    # Тип сессии: "stateful" или "stateless".
    session_type: str # "stateful" | "stateless"
    # Максимальный размер пакета, согласованный в хендшейке.
    max_packet_size: Optional[int] = None
    # Размер чанка, согласованный в хендшейке.
    chunk_size: Optional[int] = None

    # Метод для получения статуса передачи в формате, подходящем для /status.
    def get_status(self) -> dict:
        """
        Генерирует словарь со статусом передачи для эндпоинта /l7rtcp/status.
        """
        status_streams = {}
        for stream_id, stream_state in self.streams.items():
            # Преобразуем множество в отсортированный список.
            received_list = sorted(list(stream_state.received_chunks))
            
            # Простая логика определения пропущенных чанков.
            # Предполагаем, что чанки идут последовательно от 0 до максимума полученных.
            # Это упрощение; в реальном случае нужно знать total_chunks или
            # использовать более сложную логику.
            max_received = max(received_list) if received_list else -1
            missing_list = sorted(
                list(set(range(max_received + 1)) - stream_state.received_chunks)
            ) if max_received >= 0 else []
            
            status_streams[stream_id] = {
                "received": received_list,
                "missing": missing_list,
                "total": stream_state.total_chunks
            }
            
        # Проверяем, жива ли еще передача (по TTL)
        alive = True
        if self.ttl_seconds:
            elapsed_time = time.time() - self.created_at
            alive = elapsed_time <= self.ttl_seconds
            
        return {
            "transmission_id": self.id,
            "streams": status_streams,
            "ttl": int(self.ttl_seconds) if self.ttl_seconds else None,
            "alive": alive,
            # В реальности это должно быть более точное время.
            "last_received_time": self.last_received_time
        }

# Модель для запроса /resend
class ResendRequest(BaseModel):
    """Модель запроса для /l7rtcp/resend."""
    stream: str
    chunks: List[int]