# l7rtcp_poc/app/handlers.py
"""Обработчики HTTP-запросов для эндпоинтов L7RTCP."""

import time
from typing import List, Optional
from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel

# Импортируем наши модели и хранилище
from .models import (
    FeatureToggle, StreamInfo, StreamState, TransmissionState, ResendRequest
)
from .storage import storage
# Импортируем вспомогательные функции
from .utils import generate_uuid7

router = APIRouter()

# --- Вспомогательные функции для парсинга заголовков ---

def parse_features(features_str: str) -> List[FeatureToggle]:
    """Парсит строку с фичами в список FeatureToggle."""
    if not features_str:
        return []
    try:
        return [FeatureToggle(f.strip()) for f in features_str.split(',') if f.strip()]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid feature in X-Features-Supported: {e}")

def parse_streams(streams_str: Optional[str]) -> List[StreamInfo]:
    """Парсит строку с потоками в список StreamInfo."""
    if not streams_str:
        return []
    try:
        return [StreamInfo(id=s.strip()) for s in streams_str.split(',') if s.strip()]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid format in X-Streams: {e}")

# --- Обработчики эндпоинтов ---

@router.post("/l7rtcp/init")
async def init_transmission(
    request: Request,
    x_client_id: str = Header(...),
    x_features_supported: str = Header(...),
    x_session_type: str = Header(...),
    x_transmission_id: str = Header(None),
    x_streams: str = Header(None),
    x_ttl: int = Header(None),
    x_max_packet_size: int = Header(None),
    x_chunk_size: int = Header(None), # Новый заголовок из нашего обсуждения
):
    """
    Обработчик эндпоинта /l7rtcp/init.
    Выполняет хендшейк: согласование возможностей, создание/возобновление сессии.
    """
    # 1. Парсим заголовки
    features_supported = parse_features(x_features_supported)
    streams_requested = parse_streams(x_streams)
    
    # 2. Валидация обязательных параметров
    if x_session_type not in ["stateful", "stateless"]:
        raise HTTPException(status_code=400, detail="X-Session-Type must be 'stateful' or 'stateless'")
    
    # 3. Определяем или генерируем X-Transmission-ID
    transmission_id = x_transmission_id
    is_new_transmission = False
    existing_transmission = None
    
    if not transmission_id:
        # Генерируем новый ID
        transmission_id = generate_uuid7()
        is_new_transmission = True
    else:
        # Проверяем, существует ли передача с таким ID
        existing_transmission = await storage.get(transmission_id)
        if existing_transmission:
            # Это попытка возобновления
            # TODO: Проверить X-Client-ID, если он был сохранен
            # Пока что просто продолжаем работу с существующей передачей
            pass
        else:
            # Клиент предоставил ID, но передача не найдена.
            # Это либо ошибка, либо клиент хочет создать передачу с конкретным ID.
            # Для PoC будем считать это созданием новой передачи.
            is_new_transmission = True
    
    # 4. Согласование возможностей (упрощенная логика для PoC)
    # В реальности сервер должен проверять, какие фичи он поддерживает.
    # Пока что включаем все, что клиент запросил, кроме тех, которые требуют специальной логики.
    features_enabled = [FeatureToggle.CORE] # Core всегда включен
    
    # Включаем те фичи из запрошенных, которые мы планируем поддерживать в PoC
    # и которые не требуют сложной логики на данном этапе.
    supported_features_for_poc = {
        FeatureToggle.RESEND,
        FeatureToggle.TTL,
        FeatureToggle.MULTISTREAM,
        FeatureToggle.PULL, # Хотя pull опциональный, логика PoC построена на нем
        # FeatureToggle.BACKPRESSURE, # Пока не реализуем
        # FeatureToggle.PAUSE, # Пока не реализуем
        # FeatureToggle.STATELESS, # Пока не реализуем
        # FeatureToggle.FEC, # Пока не реализуем
        # FeatureToggle.METRICS, # Пока не реализуем
    }
    
    for feature in features_supported:
        if feature in supported_features_for_poc:
            features_enabled.append(feature)
    
    # 5. Подготавливаем потоки
    stream_states = {}
    if streams_requested:
        for stream_info in streams_requested:
            stream_states[stream_info.id] = StreamState(id=stream_info.id)
    
    # 6. Создаем или обновляем состояние передачи
    if is_new_transmission or not existing_transmission:
        # Создаем новую передачу
        transmission_state = TransmissionState(
            id=transmission_id,
            client_id=x_client_id,
            streams=stream_states,
            features_enabled=features_enabled,
            ttl_seconds=x_ttl,
            created_at=time.time(),
            last_received_time=time.time(), # Инициализируем временем создания
            session_type=x_session_type,
            max_packet_size=x_max_packet_size,
            chunk_size=x_chunk_size
        )
        await storage.create(transmission_state)
    else:
        # Возобновляем существующую передачу
        # В реальности нужно проверить совместимость параметров
        # Пока что просто обновляем время последнего получения
        existing_transmission.last_received_time = time.time()
        # Можно также обновить список фич, если клиент запросил новые
        # Но для простоты оставим как есть
        await storage.update(existing_transmission)
        transmission_state = existing_transmission

    # 7. Формируем ответ
    response_headers = {
        "X-Transmission-ID": transmission_state.id,
        "X-Features-Enabled": ",".join([f.value for f in features_enabled]),
    }
    
    # Добавляем опциональные заголовки в ответ
    if streams_requested:
        response_headers["X-Accepted-Streams"] = ",".join([s.id for s in streams_requested])
    if transmission_state.ttl_seconds:
        response_headers["X-TTL"] = str(transmission_state.ttl_seconds)
    if transmission_state.max_packet_size:
        response_headers["X-Max-Packet-Size"] = str(transmission_state.max_packet_size)
    if transmission_state.chunk_size:
        response_headers["X-Chunk-Size"] = str(transmission_state.chunk_size)

    return Response(status_code=status.HTTP_200_OK, headers=response_headers)


@router.post("/l7rtcp/transmit")
async def transmit_chunk(
    request: Request,
    x_transmission_id: str = Header(...),
    x_stream_id: Optional[str] = Header(None),
    x_packet_id: Optional[int] = Header(None),
    x_stream_control: Optional[str] = Header(None), # Новый опциональный заголовок
):
    """
    Обработчик эндпоинта /l7rtcp/transmit.
    Может обрабатывать как запрос/передачу чанка (с X-Stream-ID и X-Packet-ID),
    так и команды управления потоками (с X-Stream-Control).
    """
    # --- 1. Проверяем существование передачи ---
    transmission_state = await storage.get(x_transmission_id)
    if not transmission_state:
        raise HTTPException(status_code=404, detail="Transmission not found")

    # --- 2. Определяем тип запроса на основе заголовков ---
    
    # Сценарий 1: Управление потоками (если передан X-Stream-Control)
    if x_stream_control is not None:
        # В PoC просто логируем и возвращаем подтверждение
        print(f"Stream Control requested: {x_stream_control} for transmission {transmission_state.id}")
        # TODO: Реализовать парсинг x_stream_control и изменение состояния потоков
        # Например: "video;res=480=pause, audio;lang=en=resume"
        
        response_headers = {
            "X-Backpressure-Advice": "low" # Пример
        }
        # В спецификации не указан конкретный код ответа для управления потоками,
        # но 200 OK логичен для подтверждения выполнения команды.
        return Response(
            status_code=200, # 200 OK: Command processed
            headers=response_headers,
            content="Stream control command received"
        )

    # Сценарий 2: Передача/запрос чанка (если переданы X-Stream-ID и X-Packet-ID)
    elif x_stream_id is not None and x_packet_id is not None:
        # --- Это логика из оригинального transmit_chunk ---
        
        # 1. Проверяем существование потока
        if x_stream_id not in transmission_state.streams:
            raise HTTPException(status_code=400, detail=f"Stream '{x_stream_id}' not found in transmission")

        # 2. Проверяем, не истекло ли TTL (если оно было согласовано)
        if transmission_state.ttl_seconds:
            elapsed_time = time.time() - transmission_state.created_at
            if elapsed_time > transmission_state.ttl_seconds:
                raise HTTPException(status_code=410, detail="Transmission expired (TTL)")

        # 3. Генерируем фиктивные данные чанка
        chunk_size = transmission_state.chunk_size or 4096
        if transmission_state.max_packet_size and chunk_size > transmission_state.max_packet_size:
            chunk_size = transmission_state.max_packet_size
        fake_data = b"A" * chunk_size

        # 4. Обновляем состояние передачи: отмечаем, что чанк "отправлен"
        stream_state = transmission_state.streams[x_stream_id]
        stream_state.received_chunks.add(x_packet_id)
        transmission_state.last_received_time = time.time()
        await storage.update(transmission_state)

        # 5. Определяем код ответа (пока всегда 209)
        response_status_code = 209 # 209 Pending Transmission

        # 6. Формируем заголовки ответа
        response_headers = {
            "X-Backpressure-Advice": "low"
        }

        # 7. Возвращаем данные чанка в теле ответа
        return Response(
            content=fake_data,
            status_code=response_status_code,
            headers=response_headers,
            media_type="application/octet-stream"
        )

    # Сценарий 3: Некорректный набор заголовков
    else:
        # Это случай, когда переданы не все обязательные заголовки
        # для ни одного из сценариев
        missing_parts = []
        if x_stream_id is None and x_packet_id is None and x_stream_control is None:
            missing_parts.append("either (X-Stream-ID and X-Packet-ID) or (X-Stream-Control)")
        else:
            # Частично переданы заголовки
            if x_stream_id is None:
                missing_parts.append("X-Stream-ID")
            if x_packet_id is None:
                missing_parts.append("X-Packet-ID")
            if x_stream_control is None:
                # Это нормально, если мы ожидаем чанк
                pass
                
        raise HTTPException(
            status_code=400,
            detail=f"Invalid header combination. Missing: {', '.join(missing_parts)}. "
                   f"Provide either both X-Stream-ID and X-Packet-ID for chunk transmission, "
                   f"or X-Stream-Control for stream management."
        )

@router.get("/l7rtcp/status/{transmission_id}")
async def get_transmission_status(
    transmission_id: str,
    x_client_id: str = Header(None)
):
    """
    Обработчик эндпоинта /l7rtcp/status/{transmission_id}.
    Возвращает информацию о состоянии передачи.
    """
    # 1. Получаем состояние передачи
    transmission_state = await storage.get(transmission_id)
    if not transmission_state:
        raise HTTPException(status_code=404, detail="Transmission not found")

    # 2. Проверяем X-Client-ID, если он был предоставлен
    # В реальной реализации можно проверять права доступа
    # if x_client_id and transmission_state.client_id != x_client_id:
    #     raise HTTPException(status_code=403, detail="Forbidden")

    # 3. Генерируем и возвращаем статус
    # Метод get_status() уже реализован в модели TransmissionState
    return transmission_state.get_status()

@router.post("/l7rtcp/resend/{transmission_id}")
async def resend_chunks(
    transmission_id: str,
    request_data: ResendRequest,
    x_client_id: str = Header(None) # Опционально для проверки
):
    """
    Обработчик эндпоинта /l7rtcp/resend/{transmission_id}.
    Позволяет клиенту запросить повторную отправку пропущенных чанков.
    """
    # 1. Проверяем существование передачи
    transmission_state = await storage.get(transmission_id)
    if not transmission_state:
        raise HTTPException(status_code=404, detail="Transmission not found")

    # 2. Проверяем существование потока
    if request_data.stream not in transmission_state.streams:
        raise HTTPException(status_code=400, detail=f"Stream '{request_data.stream}' not found in transmission")

    # 3. В PoC просто возвращаем фиктивный ответ
    # В реальной реализации сервер должен подготовить данные для повторной отправки
    # и, возможно, отправить их (например, через WebSocket или добавить в очередь)
    
    # Для демонстрации, просто логируем запрос
    print(f"Resend requested for transmission {transmission_id}, stream {request_data.stream}, chunks {request_data.chunks}")
    
    # Возвращаем успешный статус
    return {"message": "Resend request accepted", "chunks_queued": request_data.chunks}