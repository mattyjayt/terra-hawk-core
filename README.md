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
│              │                        │  │  │ MQTT Client │  │ Video/YOLO  │  │   │
│              │                        │  │  │ (sensors)   │  │ (detection  │  │   │
│              │                        │  │  │             │  │  + tracking)│  │   │
│              │                        │  │  └────────────┘  └─────────────┘  │   │
│              │                        │  └───────────────────────────────────┘   │
└──────────────┘                        └──────────────────────────────────────────┘
```

**Data flow:**

1. **Camera** → MediaMTX captures via libcamera, serves RTSP at `rtsp://localhost:8554/stream`
2. **Video pipeline** → Reads RTSP frames, runs YOLOv26n detection + ByteTrack tracking, updates `cv_state`
3. **ESP32** → Publishes sensor JSON to MQTT topic `pi/inbox`, MQTT client updates `sensor_state`
4. **Frontend** → Connects via WebSocket to receive both streams in real time

---

## Project Structure

```
terra_hawk/
├── main.py              # FastAPI app — WebSocket endpoints & lifecycle
├── video.py             # RTSP capture, YOLO inference, ByteTrack tracking
├── mqtt_client.py       # MQTT subscriber — ESP32 sensor ingestion
├── data_models.py       # Shared state models (sensor_state, cv_state)
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
| **Inference** | Grabs the latest frame, runs YOLO detection, updates detections with ByteTrack, writes results to `cv_state` |

**Model:** [YOLOv26n](https://docs.ultralytics.com/) (nano) via Ultralytics — optimized for edge inference on the Pi's ARM CPU.

**Tracker:** [ByteTrack](https://github.com/roboflow/supervision) via the Supervision library — assigns persistent `tracker_id`s to detected objects across frames.

**Output format** (`cv_state`):

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

**Configuration** (`.env`):

| Variable | Default | Description |
|---|---|---|
| `HOST` | `localhost` | RTSP stream host |
| `RECONNECT_DELAY` | `3` | Seconds to wait before reconnecting on stream failure |
| `MAX_CONSECUTIVE_FAILURES` | `10` | Frame read failures before triggering reconnect |
| `MODEL` | `yolo26n` | Ultralytics model name or path (`.pt` / `.ncnn`) |
| `IMGSZ` | `640` | Inference input resolution |
| `CONFIDENCE` | `0.5` | Minimum detection confidence threshold |
| `IOU` | `0.7` | NMS IoU threshold |

### Model Export (`export.py`)

Utility script to export the YOLO model to **NCNN** format with FP16 quantization for faster edge inference:

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
| `GET /ping` | HTTP | Health check — returns `{"status": 200, "payload": "Hello, Jaime"}` |
| `WS /ws/sensors` | WebSocket | Pushes `sensor_state` every **200ms** (~5 updates/sec) |
| `WS /ws/cv` | WebSocket | Pushes `cv_state` every **20ms** (~50 updates/sec, matching inference rate) |

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
HOST=localhost
RECONNECT_DELAY=3
MAX_CONSECUTIVE_FAILURES=10
MODEL=yolo26n
IMGSZ=640
CONFIDENCE=0.5
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
| `ultralytics` | YOLOv26 model loading & inference |
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

---

## License

MIT

---

## References

- [MediaMTX — Raspberry Pi Cameras](https://mediamtx.org/docs/usage/publish/raspberry-pi-cameras)
- [Ultralytics YOLO Docs](https://docs.ultralytics.com/)
- [Supervision — ByteTrack](https://supervision.roboflow.com/latest/trackers/)
- [Paho MQTT Python](https://eclipse.dev/paho/files/paho.mqtt.python/html/)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
