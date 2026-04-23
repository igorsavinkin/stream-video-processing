# Streaming PC Camera to VPS for ML Processing (via Tailscale)

This document outlines how to securely stream a webcam from a local Windows PC to a remote VPS for real-time ML processing using a Tailscale VPN tunnel. 

Using Tailscale eliminates the need for public port forwarding, firewall configuration, and static IPs, while providing an encrypted, low-latency WireGuard tunnel directly between your PC and VPS.

## Architecture

```text
[PC Camera] 
    │
    ▼ 
  (FFmpeg)
[Local RTSP Server (mediamtx)] ──► (Tailscale VPN Tunnel) ──► [VPS (OpenCV / ML Model)]
(localhost:8554)                                              (100.x.x.x:8554)
```

## Prerequisites

* A Windows PC with a webcam.
* A VPS running your ML pipeline (e.g., Python, OpenCV, YOLO).
* [Tailscale](https://tailscale.com/) installed and logged in on **both** the PC and the VPS.

---

## Step 1: Configure Tailscale Network

1. Install Tailscale on your Windows PC and log into your account.
2. Install Tailscale on your VPS (Linux) (e.g., `curl -fsSL https://tailscale.com/install.sh | sh` then `sudo tailscale up`) and log into the *same* account.
3. On your **Windows PC**, open a command prompt and get your Tailscale IP:
   ```bash
   tailscale ip -4
   ```
   *Note this IP (it will look like `100.x.x.x`). This is the IP your VPS will use to reach your PC.*

---

## Step 2: Set Up Local RTSP Server on PC

FFmpeg can encode video, but it cannot act as an RTSP server by itself. We use [mediamtx](https://github.com/bluenviron/mediamtx) (formerly rtsp-simple-server) to receive the local stream and serve it.

1. Go to the [mediamtx Releases page](https://github.com/bluenviron/mediamtx/releases).
2. Download the latest `mediamtx_vX.X.X_windows_amd64.zip`.
3. Extract the `.zip` folder and double-click `mediamtx.exe`.
4. Leave this window running in the background. It is now listening on `127.0.0.1:8554`.

---

## Step 3: Stream Camera via FFmpeg

Open a new Command Prompt on your PC. We will use FFmpeg to capture the webcam, encode it efficiently for network streaming, and push it to the local mediamtx server.

First, find your camera name:
```bash
ffmpeg -list_devices true -f dshow -i dummy
```

Then, start the stream (replace `"USB Video Device"` with your actual camera name from the previous command):
```bash
ffmpeg -rtbufsize 100M -f dshow -i video="USB Video Device" -c:v libx264 -preset ultrafast -tune zerolatency -f rtsp rtsp://127.0.0.1:8554/live
```

**Why these specific flags?**
* `-rtbufsize 100M`: Prevents the `real-time buffer too full` error common with raw webcam inputs. It makes buffer size 100MB.
* `-c:v libx264 -preset ultrafast -tune zerolatency`: Encodes to H.264 with minimal CPU overhead and latency, ideal for ML inference.

---
#### Fast check of work 
1. Try to open the stream in VLC on PC:
Main menu: Media -> Open Network Stream `rtsp://100.69.204.123:8554/live`

2. Or directly in PC or VPS command line:
```
ffplay rtsp://100.69.204.123:8554/live
```
3. Check in VPS thru Python script:
```python
import cv2

# Replace with your PC's Tailscale IP from Step 1
PC_TAILSCALE_IP = "100.69.204.123" 
STREAM_URL = f"rtsp://{PC_TAILSCALE_IP}:8554/live"

cap = cv2.VideoCapture(STREAM_URL)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame")
        break
    
    # --- YOUR ML PROCESSING GOES HERE ---
    # e.g., frame = model(frame)
    # -----------------------------------

    # (Optional) If you need to view the frame, write it to a web stream or save locally
    # cv2.imwrite("debug_frame.jpg", frame)

cap.release()
```

## Step 4: Consume Stream on VPS

Your PC is now securely broadcasting the stream over your Tailscale network. 

#### Setting up application on VPS
Run the following commands on the VPS or directly edit `.env` file:

```cd /opt/stream-ml

cat > .env << 'EOF'
COMPOSE_PROJECT_NAME=stream-ml

# Камера с ПК через ngrok

APP_RTSP_URL=rtsp://100.69.204.123:8554/live     # ←- PC TAILSCALE IP 

APP_MODEL_NAME=mobilenet_v3_small
APP_DEVICE=cpu
APP_FRAME_WIDTH=640
APP_FRAME_HEIGHT=360
APP_FRAME_SAMPLE_FPS=5
APP_LOG_LEVEL=info
APP_KAFKA_BOOTSTRAP_SERVERS=
EOF
`
Reload and restart application:
```
docker compose down
docker compose up -d --force-recreate api
```

#### Verification
Open in browser:

http://178.208.88.6:8000/health
http://178.208.88.6:8000/stream

---

#### Useful commands

Restart all on VPS:
```
cd /opt/stream-ml
docker compose restart api
```

View logs:
```
docker compose logs --tail=50 api
```

## Troubleshooting

* **Connection Timeout on VPS:** Ensure Tailscale is running and logged in on *both* machines. Try pinging the PC from the VPS: `ping 100.x.x.x`.
* **Dropped Frames on PC:** If you still see `frame dropped!` in FFmpeg, try increasing `-rtbufsize` to `200M` or lowering your camera's native resolution in Windows Device Manager.
* **High Latency:** Ensure no other heavy processes are running on the PC. The `ultrafast` preset in FFmpeg is already optimized for the lowest possible latency.
```