# PC Camera → VPS ML Service

**Как настроить веб-камеру (или USB-камеру) с твоего Windows-ПК для работы с приложением на VPS**

## Общая схема

**ПК (Windows)** → FFmpeg → MediaMTX → ngrok (TCP-туннель) → **VPS** → ML-модель → `/stream`

---

## Шаг 1: Установка MediaMTX на ПК

1. Скачай последнюю версию MediaMTX:
   [https://github.com/bluenviron/mediamtx/releases](https://github.com/bluenviron/mediamtx/releases)

2. Скачай файл `mediamtx_vX.X.X_windows_amd64.zip`

3. Распакуй в удобную папку, например:
   `C:\mediamtx\`

4. Запусти `mediamtx.exe` (двойной клик).

   Должно появиться окно с надписью:
   ```
   [RTSP] listener opened on :8554
   ```

---

## Шаг 2: Запуск трансляции камеры в MediaMTX

Открой **новое** окно `PowerShell` и выполни команду:

```powershell
ffmpeg -f dshow -i video="USB Video Device" ^
  -video_size 640x360 -framerate 15 ^
  -c:v libx264 -preset ultrafast -tune zerolatency ^
  -f rtsp rtsp://localhost:8554/live
```

> Замени `"USB Video Device"` на название своей камеры (узнать можно командой `ffmpeg -list_devices true -f dshow -i dummy`).

Оставь это окно открытым.

---

## Шаг 3: Создание публичного туннеля (ngrok)

1. Скачай ngrok: [https://ngrok.com/download](https://ngrok.com/download)

2. Распакуй и положи `ngrok.exe` в удобную папку.

3. Открой **новое** окно `PowerShell` и выполни:

```powershell
ngrok tcp 8554
```

Ngrok выдаст адрес вида:
```
tcp://X.tcp.eu.ngrok.io:XXXXX
```

Скопируй этот адрес полностью.

---

## Шаг 4: Настройка приложения на VPS

На VPS выполни:

```bash
cd /opt/stream-ml

cat > .env << 'EOF'
COMPOSE_PROJECT_NAME=stream-ml

# Камера с ПК через ngrok
APP_RTSP_URL=rtsp://X.tcp.eu.ngrok.io:XXXXX/live     # ← вставь свой ngrok адрес

APP_MODEL_NAME=mobilenet_v3_small
APP_DEVICE=cpu
APP_FRAME_WIDTH=640
APP_FRAME_HEIGHT=360
APP_FRAME_SAMPLE_FPS=5
APP_LOG_LEVEL=info
APP_KAFKA_BOOTSTRAP_SERVERS=
EOF
```

Перезапусти приложение:

```bash
docker compose down
docker compose up -d --force-recreate api
```

---

## Шаг 5: Проверка

Открой в браузере:
- http://178.208.88.6:8000/health
- http://178.208.88.6:8000/stream

---

## Полезные команды

**Перезапуск всего на VPS:**
```bash
cd /opt/stream-ml
docker compose restart api
```

**Посмотреть логи:**
```bash
docker compose logs --tail=50 api
```

**Перезапуск ngrok + FFmpeg:**
Закрой окна и запусти заново.

---

## Возможные проблемы и решения

- **/stream пустой** → ngrok не запущен / FFmpeg остановился
- **I/O error в FFmpeg** → камера используется другой программой (закрой Zoom/Teams)
- **Failed to resolve hostname** → неправильный ngrok адрес
- **Высокая нагрузка** → используй `mobilenet_v3_small` и уменьши `APP_FRAME_SAMPLE_FPS`

---

## Автоматический запуск при старте Windows
Чтобы MediaMTX + FFmpeg + ngrok запускались автоматически при включении ПК:
### Вариант 1: Простой (рекомендуется для начала)

1. Создай файл `start_camera.bat` в папке `C:\mediamtx\`:

```batch
@echo off
cd C:\mediamtx

:: Запуск MediaMTX
start "" mediamtx.exe

:: Ждём 3 секунды
timeout /t 3 /nobreak >nul

:: Запуск FFmpeg (замени название камеры при необходимости)
start "" ffmpeg -f dshow -i video="USB Video Device" -video_size 640x360 -framerate 15 -c:v libx264 -preset ultrafast -tune zerolatency -f rtsp rtsp://localhost:8554/live

:: Запуск ngrok
start "" ngrok tcp 8554
```

После запуска в `PowerShell` будет отображаться:
```
Forwarding: tcp://X.tcp.eu.ngrok.io:XXXXX -> localhost:8554
```
и этот адрес `tcp://X.tcp.eu.ngrok.io:XXXXX/live` нужно будет вписать в `.env` на VPS в переменную `APP_RTSP_URL`.

2. Добавь этот .bat файл в автозагрузку:
Нажми `Win + R` → введи `shell:startup` → `Enter`
Скопируй файл `start_camera.bat` в открывшуюся папку


### Вариант 2: Более надёжный (Task Scheduler)

1. Открой Планировщик заданий (Task Scheduler)
2. Создай новое задание:
- Название: `Start Camera Stream`
- Запускать с наивысшими правами
- Запускать независимо от входа в систему

- В триггере выбери: `При запуске компьютера`  
- В Действии укажи путь к `start_camera.bat`