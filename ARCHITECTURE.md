# System Architecture

## Backend Overview

Основой системы является **FastAPI приложение** (`src/api/app.py`), которое объединяет RTSP ingestion, ML inference и API endpoints в единый сервис.

## Architecture Diagram

```
┌─────────────────────────────────────────┐
│  FastAPI (src/api/app.py)               │
│  - REST API endpoints                   │
│  - SSE streaming                        │
│  - CORS middleware                      │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
┌───▼───┐  ┌───▼───┐  ┌───▼────┐
│ RTSP  │  │ Model │  │ Metrics│
│Reader │  │Infer  │  │        │
└───────┘  └───────┘  └────────┘
```

## Core Components

### 1. FastAPI Application (`src/api/app.py`)

**Основной backend сервис**, который предоставляет:

- **REST API endpoints:**
  - `GET /health` - базовый health check
  - `GET /health/stream` - проверка доступности RTSP потока
  - `POST /predict` - предсказание на загруженном изображении
  - `GET /stream` - Server-Sent Events (SSE) поток с предсказаниями из RTSP

- **Lifespan management:**
  - Загрузка ML модели при старте приложения
  - Инициализация компонентов (metrics, capture)

- **CORS middleware:**
  - Разрешает запросы из браузера для SSE viewer

**Запуск:**
```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

### 2. RTSP Ingestion (`src/ingest/rtsp_reader.py`)

**Чтение кадров из видео источников:**

- Поддержка RTSP потоков
- Поддержка локальных видео файлов (MP4)
- Поддержка веб-камер (по индексу: 0, 1, 2...)
- Автоматическое переподключение при обрыве
- Ресайз кадров до заданного размера
- Sampling FPS (пропуск кадров для оптимизации)

**Использование:**
```python
reader = RTSPFrameReader(
    rtsp_url="rtsp://...",
    target_fps=2,
    width=640,
    height=360
).start()
frame = reader.read()
```

### 3. ML Inference (`src/model/infer.py`)

**Загрузка и использование ML моделей:**

- **MobileNetV3 Small** (по умолчанию):
  - Классификатор изображений
  - Обучен на ImageNet-1K (1000 классов)
  - Выход: top-k предсказаний с вероятностями

- **Faster R-CNN** (опционально):
  - Детектор объектов
  - Обучен на COCO (80 классов)
  - Выход: "person" / "no_person"

**Функции:**
- `load_model()` - загрузка модели и препроцессинга
- `predict_bgr()` - предсказание на BGR кадре (OpenCV)
- `predict_pil()` - предсказание на PIL изображении

### 4. Preprocessing (`src/preprocess/transforms.py`)

**Обработка изображений перед inference:**

- Конвертация BGR → RGB
- Ресайз до размера модели
- Нормализация пикселей
- Преобразование в тензор PyTorch

### 5. Metrics (`src/metrics.py`)

**Сбор метрик производительности:**

- Latency (время inference)
- FPS (кадров в секунду)
- Количество ошибок
- Периодический вывод в JSON формате для CloudWatch

**Конфигурация:**
```python
metrics = Metrics(
    log_every=50,  # логировать каждые N кадров
    dimensions={"service": "stream-ml-service"}
)
```

### 6. Configuration (`src/config.py`)

**Управление настройками:**

- Загрузка из YAML файла (`config.example.yaml`)
- Переопределение через environment variables (`APP_*`)
- Pydantic валидация настроек

**Основные настройки:**
- `rtsp_url` - источник видео
- `model_name` - модель (mobilenet_v3_small / person_detector)
- `device` - CPU/GPU
- `frame_width/height` - размер кадров
- `frame_sample_fps` - частота обработки кадров

### 7. Inference Capture (`src/inference_capture.py`)

**Опциональный захват кадров для retraining:**

- Сохранение кадров + метаданных
- Загрузка в S3 (опционально)
- Структурированное хранение по датам

## Data Flow

```
RTSP Stream
    │
    ▼
RTSPFrameReader (read frames)
    │
    ▼
Preprocessing (resize, normalize)
    │
    ▼
ML Model (inference)
    │
    ▼
Metrics (record latency)
    │
    ▼
API Response (JSON/SSE)
    │
    ▼
Client (SSE viewer / Postman)
```

## Deployment

### Local Development
```bash
uvicorn src.api.app:app --host 0.0.0.0 --port 8000
```

### Docker
```bash
docker build -t stream-ml-service .
docker run -p 8000:8000 stream-ml-service
```

### AWS ECS Fargate
- Terraform инфраструктура в `infra/`
- CI/CD через GitHub Actions
- CloudWatch логи и метрики

## Dependencies

- **FastAPI** - веб-фреймворк
- **Uvicorn** - ASGI сервер
- **PyTorch** - ML framework
- **torchvision** - предобученные модели
- **OpenCV** - обработка видео
- **Pillow** - обработка изображений

## File Structure

```
src/
├── api/
│   └── app.py          # FastAPI приложение (основной backend)
├── ingest/
│   ├── rtsp_reader.py  # RTSP ingestion
│   └── capture.py      # Dataset capture CLI
├── model/
│   ├── infer.py        # ML inference
│   └── train.py        # Model training
├── preprocess/
│   └── transforms.py  # Image preprocessing
├── config.py           # Configuration management
├── metrics.py          # Metrics collection
└── inference_capture.py # Inference data capture
```

## Summary

**Backend = FastAPI приложение**, которое:
1. Принимает RTSP поток
2. Обрабатывает кадры
3. Запускает ML модель
4. Отдаёт результаты через REST API и SSE

Вся логика сосредоточена в `src/api/app.py`, который координирует работу всех компонентов.
