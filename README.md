# Stream Video ML Service

**Реал-тайм анализ видео с помощью нейросетей**  
FastAPI + PyTorch + RTSP → JSON/SSE поток предсказаний в реальном времени.

![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PyTorch](https://img.shields.io/badge/PyTorch-EE4C2C?logo=pytorch&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-2088FF?logo=github-actions&logoColor=white)
![VPS](https://img.shields.io/badge/Deployed%20on-VPS-4CAF50)

---

## ✨ Основные возможности

- Поддержка **RTSP**, веб-камер и видеофайлов
- Реал-тайм inference на PyTorch (MobileNetV3 Small по умолчанию)
- Server-Sent Events (`/stream`) — живой поток предсказаний
- Автоматический reconnect при обрыве потока
- Оптимизированный Docker с ограничением памяти (1.5 ГБ)
- Полностью автоматический CI/CD через GitHub Actions + GHCR
- Низкое потребление ресурсов на VPS

---

## 🚀 Быстрый старт на VPS

```bash
cd /opt/stream-ml
docker compose up -d --build
```

Приложение доступно по адресу:
http://178.208.88.6:8000/docs

## Основные эндпоинты

|Метод|Путь|Описание|
|------------------------|-------------------------------|----------|
|GET|/health|Проверка работоспособности|
|GET|/stream|Главный — живой SSE-поток предсказаний|
|POST|/predict|Предсказание на одном изображении|
|GET|/health/stream|Проверка подключения к источнику видео| 
 

## Текущий статус на VPS

 - Ветка: `vps_deploy`
 - Источник видео: `test.mp4` (локальный файл (at VPS) для тестирования)
 - Модель: `mobilenet_v3_small`
 - Kafka: отключён
 - Память: ограничена `1.5 ГБ` на сервис api
 - CI/CD: полностью настроен (GitHub Actions → GHCR → VPS)


## Автоматический деплой
Каждый `git push` в ветку `vps_deploy` автоматически:

- Собирает Docker-образ
- Пушит в GitHub Container Registry (GHCR)
- VPS подтягивает новый образ и перезапускает контейнер

**main** ветка остаётся чистой для портфолио и демонстрации.

##  Как обновить проект
```Bash
git checkout vps_deploy
# вносишь изменения
git add .
git commit -m "описание изменения"
git push origin vps_deploy
```

## ML Модели

 - MobileNetV3 Small (по умолчанию) — быстрая классификация изображений (1000 классов ImageNet)
 - Faster R-CNN Person Detector (опционально) — определение наличия человека

Переключение модели:

```Bash
# В .env
APP_MODEL_NAME=mobilenet_v3_small     # или person_detector
```

## Структура проекта

- src/ — основной код
- docker-compose.yml — конфигурация с лимитами памяти
- Dockerfile — оптимизированная multi-stage сборка
- ARCHITECTURE.md — подробная архитектура


Автор: Igor Savinkin
Статус: Активная разработка на VPS (ветка `vps_deploy`)