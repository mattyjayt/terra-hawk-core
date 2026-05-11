# 🦅 TerraHawk — Edge CV & IoT Backend

TerraHawk is a distributed edge backend for a smart farm monitoring platform. It combines **real-time computer vision** (object detection + tracking) with **IoT sensor ingestion** via MQTT, serving everything through a **FastAPI** backend over WebSockets to the [TerraHawk frontend](https://github.com/your-org/verdant-precision).

The system supports **multiple distributed systems** — each with its own controller, camera, sensors, and actuators — managed through a central registry.

---

## Architecture

```
┌──────────────┐                        ┌──────────────────────────────────────────┐
│  System 01   │                        │        Central Backend (Pi 5)            │
│  ESP32 MCU   │  MQTT (pub)            │                                          │
│  (sensors)   │ ──────────────────►    │  ┌─────────────┐    ┌────────────────┐   │
└──────────────┘  terrahawk/sys-01/     │  │  HiveMQ Cloud │    │   MediaMTX      │   │
                  sensors               │  │ (MQTTS 8883) │    │  (RTSP 8554)   │   │
┌──────────────┐                        │  └──────┬──────┘    └───────┬────────┘   │
│  System 02   │  MQTT / MJPEG          │         │                   │            │
│  ESP32-CAM   │ ──────────────────►    │  ┌──────▼───────────────────▼────────┐   │
│  (future)    │                        │  │         FastAPI (main.py)          │   │
└──────────────┘                        │  │                                    │   │
                                        │  │  ┌────────────┐  ┌─────────────┐  │   │
┌──────────────┐       WebSocket        │  │  │ MQTT Client │  │   CV Engine │  │   │
│   Frontend   │ ◄──────────────────    │  │  │ (per-system)│  │ YOLO/RF-DETR│  │   │
│  (React/TS)  │   /ws/sensors/{id}     │  │  │             │  │ (per-system)│  │   │
│              │   /ws/cv/{id}          │  │  └────────────┘  └─────────────┘  │   │
│              │   /systems             │  │                                    │   │
└──────────────┘                        │  │  ┌──────────────────────────────┐  │   │
                                        │  │  │ System Registry (systems.json)│  │   │
                                        │  │  └──────────────────────────────┘  │   │
                                        │  └───────────────────────────────────┘   │
                                        └──────────────────────────────────────────┘
```

**Data flow:**

1. **Camera** → MediaMTX captures via libcamera, serves RTSP at `rtsp://localhost:8554/stream`
2. **Video pipeline** → Per-system reader + inference threads run detection (YOLO or RF-DETR) + ByteTrack tracking, update per-system `cv_state`
3. **ESP32** → Publishes sensor JSON to namespaced MQTT topic `terrahawk/{system_id}/sensors`, MQTT client routes to per-system `sensor_state`
4. **Frontend** → Connects via WebSocket to receive per-system streams, fetches system registry from `GET /systems`

---

## Distributed System Registry

TerraHawk supports multiple distributed systems managed through a central `systems.json` registry. Each **System** is a physical deployment unit with a controller and optional components.

### System Model

```
System = a deployment unit at a physical location
├── Controller    (required) — Pi, ESP32, or Arduino
├── Camera        (optional) — Pi Camera, ESP32-CAM, USB cam
├── Sensors       (optional) — DHT, soil, light, etc.
└── Actuators     (optional) — relay, pump, fan, motor
```

### Registry (`systems.json`)

```json
{
  "systems": [
    {
      "id": "sys-01",
      "name": "Chamber 01",
      "location": "Nursery",
      "controller": {
        "type": "raspberry-pi",
        "ip": "localhost"
      },
      "components": {
        "camera": {
          "type": "pi-camera-3",
          "stream_url": "rtsp://localhost:8554/stream",
          "whep_url": "http://192.168.178.147:8889/stream/whep",
          "inference": {
            "enabled": true,
            "runs_on": "self"
          }
        },
        "sensors": {
          "type": "esp32-mqtt",
          "mqtt_topic_in": "terrahawk/sys-01/sensors",
          "mqtt_topic_out": "terrahawk/sys-01/commands",
          "capabilities": ["temperature", "humidity", "soil"]
        },
        "actuators": {
          "actions": ["fan_on", "fan_off", "pump_on", "pump_off"]
        }
      }
    }
  ]
}
```

### Adding a New System

1. Edit `systems.json` — add a new entry with `id`, `name`, `location`, `controller`, and `components`
2. Restart the backend — `./start.sh`
3. The new system's camera stream gets its own inference pipeline automatically
4. The frontend picks up the new system from `GET /systems`

### Inference Location (`runs_on`)

| Controller | Camera | `runs_on` | Why |
|---|---|---|---|
| **Pi 5** | Pi Camera 3 | `"self"` | Pi has the CPU for YOLO/RF-DETR |
| **ESP32-CAM** | Built-in OV2640 | `"central"` | ESP32 can't run YOLO — it streams MJPEG, central pulls and runs inference |
| **Pi Zero** | USB cam | `"central"` | Pi Zero too weak for real-time inference |

### Health Monitoring

A background thread pings each system's controller IP every 30 seconds. Status is returned via `GET /systems` as `"online"`, `"offline"`, or `"unknown"`.

---

## Project Structure

```
terra_hawk/
├── main.py              # FastAPI app — REST + WebSocket endpoints & lifecycle
├── video.py             # Per-system RTSP/MJPEG capture, YOLO/RF-DETR inference, ByteTrack
├── systems.py           # System registry loader, health monitoring, accessors
├── systems.json         # Distributed system definitions (controllers, cameras, sensors)
├── config.py            # Thread-safe runtime config, model registry, hot-swap
├── mqtt_client.py       # MQTT subscriber — namespaced per-system sensor ingestion
├── data_models.py       # Per-system shared state (sensor, cv, inference stats)
├── export.py            # Model export utility (PyTorch → NCNN)
├── .env                 # Runtime configuration (model, stream, thresholds)
├── pyproject.toml       # Project metadata & dependencies (uv)
├── install.sh           # One-shot MediaMTX installer
├── start.sh             # Launch script (MediaMTX + FastAPI, binds 0.0.0.0)
├── mediamtx/            # MediaMTX binary & config (gitignored)
│   ├── mediamtx         # Server binary
│   ├── mediamtx.yml     # Customized config
│   └── mediamtx.yml.original
└── .venv/               # Python virtual environment (gitignored)
```

---

## Computer Vision Pipeline

### Detection & Tracking (`video.py`)

On startup, `start_pipelines()` iterates all systems with cameras in the registry and spawns **two daemon threads per system**:

| Thread | Purpose |
|---|---|
| **Reader** | Connects to the system's stream URL (RTSP or MJPEG), reads frames as fast as possible, keeps only the latest frame (drop-oldest) |
| **Inference** | Grabs the latest frame, runs detection via the shared model, updates per-system `cv_state` and `inference_stats` |

All systems share a single model instance. Each system has its own ByteTrack tracker (independent tracking IDs per camera).

### Supported Model Families

| Family | Models | API | Notes |
|---|---|---|---|
| **YOLO** (Ultralytics) | `yolo26n`, `best`, any `.pt` / `_ncnn_model` | `model(source, imgsz, conf, iou)` → convert to `sv.Detections` | Supports `imgsz` and `iou` parameters |
| **RF-DETR** (Roboflow) | `rfdetr-nano`, `rfdetr-small` | `model.predict(frame, threshold)` → returns `sv.Detections` directly | CPU-only on Pi (`device="cpu"`), uses `threshold` only (no `iou`/`imgsz`) |

Three abstraction functions handle the differences:

- `load_model(name)` — instantiates the correct model class
- `run_inference(model, frame, cfg)` — calls the appropriate predict API
- `get_class_names(model)` — extracts class labels from either model type

### Model Hot-Swap

Models can be changed at runtime via `PUT /settings` without restarting the server. The inference thread checks for swap requests each iteration, loads the new model, and resets all per-system trackers.

### Available Models

| Name | Format | Size | Source |
|---|---|---|---|
| `yolo26n` | PyTorch | 5.3 MB | Local `.pt` file |
| `best` | PyTorch | 5.1 MB | Local `.pt` file (fine-tuned) |
| `best_ncnn_model` | NCNN | 4.7 MB | Local directory (exported) |
| `rfdetr-nano` | RF-DETR | ~349 MB | Auto-downloaded on first use |
| `rfdetr-small` | RF-DETR | ~349 MB | Auto-downloaded on first use |

**Tracker:** [ByteTrack](https://github.com/roboflow/supervision) via Supervision — per-system persistent `tracker_id`s across frames.

### Output Format (`cv_state` — per system)

```json
{
  "timestamp": 1714142400.123,
  "resolution": "640x640",
  "objects": [
    {
      "id": 1,
      "label": "person",
      "confidence": 0.872,
      "bbox": {
        "x": 0.12,
        "y": 0.34,
        "width": 0.15,
        "height": 0.40
      }
    }
  ]
}
```

All bounding box coordinates are **normalized** (0.0–1.0), resolution-independent.

---

## Runtime Configuration (`config.py`)

Thread-safe config store. Settings can be changed at runtime via the REST API without restarting.

### Environment Variables (`.env`)

```env
# Stream Configuration
HOST=localhost
RECONNECT_DELAY=3.0
MAX_CONSECUTIVE_FAILURES=10

# Detection & Tracking Configuration
# MODEL options:
#   YOLO:     yolo26n, best (local .pt files)
#   NCNN:     best_ncnn_model (local directory)
#   RF-DETR:  rfdetr-nano, rfdetr-small (auto-downloaded, CPU-only)
MODEL=rfdetr-nano
IMGSZ=640
CONFIDENCE=0.5
# IOU is used by YOLO only (RF-DETR does not support NMS IOU threshold)
IOU=0.7
```

| Variable | Default | Description |
|---|---|---|
| `MQTT_BROKER` | — | HiveMQ Cloud hostname |
| `MQTT_PORT` | `8883` | MQTT broker port (TLS) |
| `MQTT_USER_PI` | — | MQTT username for Pi client |
| `MQTT_PASS_PI` | — | MQTT password for Pi client |
| `HOST` | `localhost` | RTSP stream host |
| `RECONNECT_DELAY` | `3` | Seconds before reconnecting on stream failure |
| `MAX_CONSECUTIVE_FAILURES` | `10` | Frame read failures before triggering reconnect |
| `MODEL` | `yolo26n` | Model name — see available models table |
| `IMGSZ` | `640` | Inference resolution (YOLO only) |
| `CONFIDENCE` | `0.5` | Minimum detection confidence |
| `IOU` | `0.7` | NMS IoU threshold (YOLO only) |

### Model Export (`export.py`)

Export YOLO to NCNN with FP16 quantization:

```bash
uv run python export.py
```

---

## IoT Sensor Ingestion — ESP32 via MQTT

### Protocol

ESP32 microcontrollers publish sensor readings over MQTT to **HiveMQ Cloud** (TLS, port 8883). Topics are **namespaced by system ID**.

| Parameter | Value |
|---|---|
| **Broker** | HiveMQ Cloud (TLS, port 8883) |
| **Sensor topic pattern** | `terrahawk/{system_id}/sensors` |
| **Command topic pattern** | `terrahawk/{system_id}/commands` |
| **Backend subscribes to** | `terrahawk/+/sensors` (wildcard) |
| **Legacy support** | `pi/inbox` (routes to default system) |
| **QoS** | Default (0) |

### ESP32 Payload Schema

Published to `terrahawk/sys-01/sensors`:

```json
{
  "status": "Online",
  "temperature": 24.5,
  "humidity": 62.3,
  "soil": 742
}
```

### Sensor State (`sensor_state` — per system)

```json
{
  "status": "Online",
  "temperature": 24.5,
  "humidity": 62.3,
  "soil": 742,
  "soil": 0
}
```

| Field | Type | Source |
|---|---|---|
| `status` | `string` | ESP32 (`"Online"` / `"idle"`) |
| `temperature` | `float \| null` | DHT sensor (°C) |
| `humidity` | `float \| null` | DHT sensor (%) |
| `soil` | `int` | Soil moisture (analog pin 36 on ESP32) |

### Current ESP32 Configuration

- **Broker:** HiveMQ Cloud (TLS, port 8883)
- **Sensor:** DHT11 on pin 18, soil moisture (analog pin 36), SSD1306 OLED (I2C: SDA=13, SCL=14)
- **Publishes to:** `terrahawk/sys-01/sensors`
- **Subscribes to:** `terrahawk/sys-01/commands`

---

## FastAPI Backend (`main.py`)

### Endpoints

| Endpoint | Type | Description |
|---|---|---|
| `GET /ping` | HTTP | Health check |
| `GET /systems` | HTTP | List all systems with live status |
| `GET /systems/{system_id}` | HTTP | Single system details |
| `GET /settings` | HTTP | Current config + defaults + inference stats |
| `GET /settings/models` | HTTP | Available models with name, format, size |
| `PUT /settings` | HTTP | Partial config update — 422 on invalid, 404 on missing model |
| `WS /ws/sensors/{system_id}` | WebSocket | Per-system sensor stream (5 Hz) |
| `WS /ws/cv/{system_id}` | WebSocket | Per-system CV detection stream (~50 Hz) |
| `WS /ws/sensors` | WebSocket | Legacy — default system sensor stream |
| `WS /ws/cv` | WebSocket | Legacy — default system CV stream |

### Startup

1. System registry loaded from `systems.json`
2. Per-system state dicts initialised in `data_models.py`
3. MQTT client connects and subscribes to `terrahawk/+/sensors`
4. Per-system video pipelines spawned (reader + inference threads per camera)
5. Health monitoring thread begins pinging controllers

CORS is fully open (`allow_origins=["*"]`) for development.

---

## MediaMTX — Camera Streaming

MediaMTX captures from the Raspberry Pi Camera Module via libcamera and serves over multiple protocols.

### Stream URLs

| Protocol | URL |
|---|---|
| RTSP | `rtsp://<pi-ip>:8554/stream` |
| WebRTC | `http://<pi-ip>:8889/stream` |
| HLS | `http://<pi-ip>:8888/stream` |

### Camera Configuration

```yaml
paths:
  stream:
    source: rpiCamera
    rpiCameraWidth: 640
    rpiCameraHeight: 640
    rpiCameraFPS: 15
```

### Production Streaming (Cloudflare Tunnel + coturn)

For public access via `terra-hawk.com`, the stream is served over WebRTC (WHEP) through a Cloudflare Tunnel:

```
Browser ←→ Cloudflare Tunnel ←→ MediaMTX WHEP (port 8889)
               (signaling)
Browser ←→ coturn TURN relay  ←→ MediaMTX WebRTC (UDP 8189)
               (media)
```

| Service | Port | Purpose |
|---|---|---|
| MediaMTX RTSP | 8554 | Internal — CV pipeline consumes this |
| MediaMTX HLS | 8888 | Fallback stream (`stream.terra-hawk.com`) |
| MediaMTX WHEP | 8889 | Primary stream (`rtc.terra-hawk.com`) — ~10ms latency |
| coturn TURN | 3478 | WebRTC media relay for NAT traversal |

**Cloudflare Tunnel config** (`/etc/cloudflared/config.yml`):

```yaml
ingress:
  - hostname: rtc.terra-hawk.com
    service: http://localhost:8889
  - hostname: stream.terra-hawk.com
    service: http://localhost:8888
  - hostname: api.terra-hawk.com
    service: http://localhost:8000
  - service: http_status:404
```

**coturn config** (`/etc/turnserver.conf`):

```conf
listening-port=3478
realm=terra-hawk.com
static-auth-secret=<secret>
no-cli
no-tls
no-dtls
no-multicast-peers
```

**MediaMTX ICE config** (`mediamtx.yml`):

```yaml
webrtcICEServers2:
  - url: turn:localhost:3478
    username: any
    password: <same-secret-as-coturn>
```

**Latency comparison:**

| Method | Latency | Notes |
|---|---|---|
| HLS through tunnel | ~8000ms | Segment-based, inherent floor |
| WebRTC (WHEP) through tunnel | ~10ms | Signaling via tunnel, media via TURN |

---

## Prerequisites

- **Raspberry Pi 5** (8GB recommended) running Pi OS Bookworm 64-bit
- **Raspberry Pi Camera Module** (v2/v3/HQ) — verify with `rpicam-hello`
- **HiveMQ Cloud account** — MQTT broker (TLS, port 8883)
- **ESP32** with DHT + soil moisture + OLED, flashed with MQTT/TLS firmware
- **[uv](https://docs.astral.sh/uv/)** — Python package manager

---

## Installation

### 1. Clone & install dependencies

```bash
git clone https://github.com/your-org/terra-hawk-backend.git
cd terra-hawk-backend
uv sync
```

### 2. Install MediaMTX

```bash
chmod +x install.sh
./install.sh
```

### 3. Install coturn (production streaming)

```bash
sudo apt install coturn -y
sudo systemctl enable coturn
```

Configure `/etc/turnserver.conf` — see [Production Streaming](#production-streaming-cloudflare-tunnel--coturn) above.

### 4. Configure `.env`

See [Runtime Configuration](#runtime-configuration-configpy) above.

### 5. Configure `systems.json`

Define your systems. See [Distributed System Registry](#distributed-system-registry) above.

### 6. Configure MQTT credentials

Add HiveMQ Cloud credentials to `.env`:

```env
MQTT_BROKER=<your-hivemq-host>
MQTT_PORT=8883
MQTT_USER_PI=rasp-pi
MQTT_PASS_PI=<password>
```

> **TODO:** TLS cert pinning for production. Currently using `setInsecure()` on ESP32.

---

## Running

```bash
chmod +x start.sh   # first time only
./start.sh
```

This launches:
1. **MediaMTX** in the background (camera → RTSP, logs to `mediamtx/mediamtx.log`)
2. **FastAPI** via uvicorn on `0.0.0.0:8000` (accessible from all network interfaces)

Press `Ctrl+C` to shut down both processes cleanly.

---

## Git Ignored

| Path | Reason |
|---|---|
| `mediamtx/` | Large binary (~30MB), installed via `install.sh` |
| `*.pt` | PyTorch model weights |
| `*.pth` | RF-DETR pretrained weights |
| `*_model` | Exported model directories (NCNN) |
| `.venv/` | Python virtual environment |
| `.env` | Local configuration |
| `*.log` | Runtime logs |
| `__pycache__/` | Python bytecode |

---

## Dependencies

From `pyproject.toml` (Python ≥ 3.12):

| Package | Purpose |
|---|---|
| `fastapi` + `uvicorn` | Async web framework & ASGI server |
| `ultralytics` | YOLO model loading & inference |
| `rfdetr` | RF-DETR model loading & inference |
| `supervision` | ByteTrack tracking + detection utilities |
| `opencv-python` | RTSP/MJPEG frame capture |
| `paho-mqtt` | MQTT client for ESP32 sensor data |
| `ncnn` + `pnnx` | NCNN inference backend & model converter |
| `python-dotenv` | `.env` file loading |
| `aiortc` | WebRTC support |
| `websockets` | WebSocket protocol support |

---

## Troubleshooting

| Issue | Cause | Fix |
|---|---|---|
| `path 'stream' is not configured` | MediaMTX not reading config | Check `start.sh` passes config path to binary |
| `ERR [RPI Camera source] process exited` | libcamera not working | Run `rpicam-hello` to diagnose |
| Stream connects but drops | Bad resolution/FPS or cable | Check `mediamtx.log` |
| No sensor data | HiveMQ Cloud unreachable, ESP32 offline, or MQTT creds wrong | Check `.env` MQTT credentials, verify ESP32 connects to HiveMQ with TLS |
| RF-DETR `Found no NVIDIA driver` | RF-DETR trying to use CUDA | Ensure `video.py` passes `device="cpu"` |
| RF-DETR slow / OOM | 349MB model on Pi | Use YOLO models for real-time; RF-DETR for accuracy testing |
| Frontend can't connect to API | uvicorn binding to localhost only | Ensure `start.sh` has `--host 0.0.0.0` |
| Duplicate system IDs | Config error in `systems.json` | Each system must have a unique `id` |

---

## License

MIT

---

## References

- [MediaMTX — Raspberry Pi Cameras](https://mediamtx.org/docs/usage/publish/raspberry-pi-cameras)
- [Ultralytics YOLO Docs](https://docs.ultralytics.com/)
- [RF-DETR (Roboflow)](https://github.com/roboflow/rf-detr)
- [Supervision — ByteTrack](https://supervision.roboflow.com/latest/trackers/)
- [Paho MQTT Python](https://eclipse.dev/paho/files/paho.mqtt.python/html/)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
