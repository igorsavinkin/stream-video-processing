## Локальный RTSP-сервер - MediaMTX
У вас запущена программа MediaMTX (mediamtx.exe).

Это локальный RTSP-сервер, который упоминался в файле README.md проекта. Эта программа выступает в роли "ретранслятора" видео:

Вы через процесс ffmpeg отправляете в неё видеофайл с камеры или жесткого диска:

```
ffmpeg -re -stream_loop -1 -i "C:/Users/igors/Videos/WST/WST-graduation-Video-2025-12-31.mp4" -c copy -f rtsp rtsp://localhost:8554/live
```
MediaMTX принимает этот поток и раздает его по адресу `rtsp://localhost:8554/live`
Ваше приложение на FastAPI подключается к этому адресу, чтобы забирать кадры и отправлять их в нейросеть (MobileNetV3).