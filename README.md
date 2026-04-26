# 🦅 TerraHawk — Edge CV & IoT Backend

TerraHawk is the edge backend for a smart farm monitoring platform, running on a Raspberry Pi 5. It combines **real-time computer vision** (object detection + tracking) with **IoT sensor ingestion** via MQTT, serving everything through a **FastAPI** backend over WebSockets to the [TerraHawk frontend](https://github.com/your-org/terra-hawk-frontend).

---

## Architecture

```
┌──────────────┐       MQTT (pub)       ┌──────────────────────────────────────────┐
│   ESP32 MCU  │ ────────────────────►  │          Raspberry Pi 5                  │
│  (sensors)   │   pi/inbox             │                                          │
└──────────────┘                        │  ┌─────────────┐    ┌────────────────┐   │
                                        │  │  Mosquitto   │    │   MediaMTX      │   │
┌──────────────┐       WebSocket        │  │  (MQTT 1883) │    │  (RTSP 8554)   │   │
│   Frontend   │ ◄──────────────────    │  └──────┬──────┘    └───────┬────────┘   │
│  (React/TS)  │   /ws/sensors          │         │                   │            │
│              │   /ws/cv               │  ┌──────▼───────────────────▼────────┐   │
│              │                        │  │         FastAPI (main.py)          │   │
│              │                        │  │  ┌────────────┐  ┌─────────────┐  │   │
│              │                        │  │  │ MQTT Client │  │   CV Engine │  │   │
│              │                        │  │  │ (sensors)   │  │ YOLO/RF-DETR│  │   │
│              │                        │  │  │             │  │  + tracking │  │   │
│              │                        │  │  └────────────┘  └─────────────┘  │   │
│              │                        │  └───────────────────────────────────┘   │
└──────────────┘                        └──────────────────────────────────────────┘
```

**Data flow:**

1. **Camera** → MediaMTX captures via libcamera, serves RTSP at `rtsp://localhost:8554/stream`
2. **Video pipeline** → Reads RTSP frames, runs detection (YOLO or RF-DETR) + ByteTrack tracking, updates `cv_state`
3. **ESP32** → Publishes sensor JSON to MQTT topic `pi/inbox`, MQTT client updates `sensor_state`
4. **Frontend** → Connects via WebSocket to receive both streams in real time

---

## Project Structure

```
terra_hawk/
├── main.py              # FastAPI app — REST + WebSocket endpoints & lifecycle
├── video.py             # RTSP capture, unified YOLO/RF-DETR inference, ByteTrack tracking
├── config.py            # Thread-safe runtime config store, model registry, hot-swap support
├── mqtt_client.py       # MQTT subscriber — ESP32 sensor ingestion
├── data_models.py       # Shared state models (sensor_state, cv_state, inference_stats)
├── export.py            # Model export utility (PyTorch → NCNN)
├── .env                 # Runtime configuration (model, stream, thresholds)
├── pyproject.toml       # Project metadata & dependencies (uv)
├── install.sh           # One-shot MediaMTX installer
├── start.sh             # Launch script (MediaMTX + FastAPI)
├── mediamtx/            # MediaMTX binary & config (gitignored)
│   ├── mediamtx         # Server binary
│   ├── mediamtx.yml     # Customized config
│   └── mediamtx.yml.original
└── .venv/               # Python virtual environment (gitignored)
```

---

## Computer Vision Pipeline

### Detection & Tracking (`video.py`)

The CV pipeline runs two daemon threads launched at FastAPI startup:

| Thread | Purpose |
|---|---|
| **Reader** | Connects to the RTSP stream, reads frames as fast as possible, keeps only the latest frame (drop-oldest strategy to avoid lag) |
| **Inference** | Grabs the latest frame, runs detection via the active model, updates detections with ByteTrack, writes results to `cv_state` and `inference_stats` |

### Supported Model Families

The inference engine supports two model families through a unified abstraction layer:

| Family | Models | API | Notes |
|---|---|---|---|
| **YOLO** (Ultralytics) | `yolo26n`, `best`, any `.pt` / `_ncnn_model` | `model(source, imgsz, conf, iou)` → convert to `sv.Detections` | Supports `imgsz` and `iou` parameters |
| **RF-DETR** (Roboflow) | `rfdetr-nano`, `rfdetr-small` | `model.predict(frame, threshold)` → returns `sv.Detections` directly | CPU-only on Pi (`device="cpu"`), uses `threshold` only (no `iou`/`imgsz`) |

Three abstraction functions in `video.py` handle the differences:

- `load_model(name)` — instantiates the correct model class
- `run_inference(model, frame, cfg)` — calls the appropriate predict API
- `get_class_names(model)` — extracts class labels from either model type

### Model Hot-Swap

Models can be changed at runtime via `PUT /settings` without restarting the server. The inference thread checks for swap requests each iteration, loads the new model, and resets the tracker.

### Available Models

| Name | Format | Size | Source |
|---|---|---|---|
| `yolo26n` | PyTorch | 5.3 MB | Local `.pt` file |
| `best` | PyTorch | 5.1 MB | Local `.pt` file (fine-tuned) |
| `best_ncnn_model` | NCNN | 4.7 MB | Local directory (exported) |
| `rfdetr-nano` | RF-DETR | ~349 MB | Auto-downloaded on first use |
| `rfdetr-small` | RF-DETR | ~349 MB | Auto-downloaded on first use |

**Tracker:** [ByteTrack](https://github.com/roboflow/supervision) via the Supervision library — assigns persistent `tracker_id`s to detected objects across frames. Works with both model families since both output `sv.Detections`.

### Output Format (`cv_state`)

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

All bounding box coordinates are **normalized** (0.0–1.0) relative to the frame resolution, making them resolution-independent for the frontend.

### Inference Stats (`inference_stats`)

Updated every frame, exposed via `GET /settings`:

```json
{
  "fps": 12.3,
  "latency_ms": 81.2,
  "active_tracks": 3
}
```

---

## Runtime Configuration (`config.py`)

All runtime settings are centralised in a thread-safe config module, replacing scattered `.env` reads. Settings can be changed at runtime via the REST API without restarting the server.

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
| `HOST` | `localhost` | RTSP stream host |
| `RECONNECT_DELAY` | `3` | Seconds to wait before reconnecting on stream failure |
| `MAX_CONSECUTIVE_FAILURES` | `10` | Frame read failures before triggering reconnect |
| `MODEL` | `yolo26n` | Model name — see available models table above |
| `IMGSZ` | `640` | Inference input resolution (YOLO only, ignored by RF-DETR) |
| `CONFIDENCE` | `0.5` | Minimum detection confidence threshold |
| `IOU` | `0.7` | NMS IoU threshold (YOLO only, ignored by RF-DETR) |

### Model Export (`export.py`)

Utility script to export a YOLO model to **NCNN** format with FP16 quantization for faster edge inference:

```bash
uv run python export.py
```

This produces an NCNN model directory that can be referenced in `.env` as `MODEL=yolo26n_ncnn_model` for optimized ARM inference.

---

## IoT Sensor Ingestion — ESP32 via MQTT

### Protocol

The ESP32 microcontroller publishes sensor readings over **MQTT** to a local Mosquitto broker running on the Pi.

| Parameter | Value |
|---|---|
| **Broker** | `localhost:1883` |
| **Subscribe topic** | `pi/inbox` (Pi listens) |
| **Publish topic** | `esp32/inbox` (available for Pi → ESP32 commands) |
| **QoS** | Default (0) |

### ESP32 Payload Schema

The ESP32 publishes JSON to `pi/inbox`:

```json
{
  "status": "active",
  "temperature": 24.5,
  "humidity": 62.3
}
```

### Sensor State (`sensor_state`)

The MQTT client parses incoming messages and updates the shared state:

```json
{
  "status": "active",
  "temperature": 24.5,
  "humidity": 62.3,
  "soil": 0
}
```

| Field | Type | Source |
|---|---|---|
| `status` | `string` | ESP32 (`"active"` / `"idle"`) |
| `temperature` | `float \| null` | DHT sensor (°C) |
| `humidity` | `float \| null` | DHT sensor (%) |
| `soil` | `int` | Soil moisture — reserved (hardcoded `0` pending sensor integration) |

> **Note:** The `soil` field is a placeholder. The soil moisture sensor is planned but not yet wired to the ESP32.

---

## FastAPI Backend (`main.py`)

### Endpoints

| Endpoint | Type | Description |
|---|---|---|
| `GET /ping` | HTTP | Health check |
| `GET /settings` | HTTP | Current config + defaults + live inference stats |
| `GET /settings/models` | HTTP | Available models with name, format, and file size |
| `PUT /settings` | HTTP | Partial config update (model, confidence, IOU, imgsz) — 422 on invalid, 404 on missing model |
| `WS /ws/sensors` | WebSocket | Pushes `sensor_state` every **200ms** (~5 Hz) |
| `WS /ws/cv` | WebSocket | Pushes `cv_state` every **20ms** (~50 Hz) |

### Startup

On application startup, `main.py` launches the video pipeline threads (reader + inference) via `start_thread()`. The MQTT client is initialized at module import and begins listening immediately.

CORS is fully open (`allow_origins=["*"]`) for development — the frontend connects from a separate host.

---

## MediaMTX — Camera Streaming

MediaMTX captures directly from the Raspberry Pi Camera Module via libcamera and serves the stream over multiple protocols.

### Stream URLs

| Protocol | URL |
|---|---|
| RTSP | `rtsp://<pi-ip>:8554/stream` |
| WebRTC | `http://<pi-ip>:8889/stream` |
| HLS | `http://<pi-ip>:8888/stream` |

### Camera Configuration

Default settings in `mediamtx.yml`:

```yaml
paths:
  stream:
    source: rpiCamera
    rpiCameraWidth: 640
    rpiCameraHeight: 640
    rpiCameraFPS: 15
```

See the `mediamtx.yml.original` file for all available `rpiCamera*` settings (resolution, FPS, autofocus, bitrate, flip, etc.).

---

## Prerequisites

- **Raspberry Pi 5** (8GB recommended) running Pi OS Bookworm 64-bit
- **Raspberry Pi Camera Module** (v2/v3/HQ) — verify with `rpicam-hello`
- **Mosquitto MQTT broker** — install with `sudo apt install mosquitto`
- **ESP32** with DHT temperature/humidity sensor, flashed with MQTT publish firmware
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

This fetches the latest MediaMTX release, extracts it to `mediamtx/`, and patches the config for the Pi camera.

### 3. Configure `.env`

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

### 4. Start Mosquitto

```bash
sudo systemctl start mosquitto
```

---

## Running

```bash
chmod +x start.sh   # first time only
./start.sh
```

This launches:
1. **MediaMTX** in the background (camera → RTSP stream, logs to `mediamtx/mediamtx.log`)
2. **FastAPI** via uvicorn in the foreground (with hot reload)

Press `Ctrl+C` to shut down both processes cleanly.

The API is available at `http://<pi-ip>:8000`.

---

## Git Ignored

The following are excluded from version control to save space:

| Path | Reason |
|---|---|
| `mediamtx/` | Large binary (~30MB), installed via `install.sh` |
| `*.pt` | PyTorch model weights (downloaded by Ultralytics on first run) |
| `*.pth` | RF-DETR pretrained weights (auto-downloaded) |
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
| `rfdetr` | RF-DETR model loading & inference (Roboflow) |
| `supervision` | ByteTrack object tracking + detection utilities |
| `opencv-python` | RTSP frame capture & image processing |
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
| `WAR configuration file not found` | Binary falling back to CWD | Verify `MEDIAMTX_CONF` path in `start.sh` |
| `ERR [RPI Camera source] process exited` | libcamera not working | Run `rpicam-hello` to diagnose |
| Stream connects but drops | Bad resolution/FPS or cable | Check `mediamtx.log` |
| No sensor data | Mosquitto not running or ESP32 offline | `sudo systemctl status mosquitto` |
| YOLO model download fails | No internet on Pi | Pre-download `.pt` on another machine, copy over |
| RF-DETR `Found no NVIDIA driver` | RF-DETR trying to use CUDA on Pi | Ensure `video.py` passes `device="cpu"` to RF-DETR constructors |
| RF-DETR slow / OOM | 349MB model on 8GB Pi | Use YOLO models for real-time; RF-DETR for accuracy testing |

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
