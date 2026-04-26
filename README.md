# MediaMTX — Raspberry Pi Camera Streaming

MediaMTX (formerly `rtsp-simple-server`) is a media server that can capture directly from the Raspberry Pi camera module via libcamera and re-stream it over RTSP, WebRTC, HLS, RTMP, and SRT — all without needing external tools like `rpicam-vid` or `ffmpeg`.

---

## Prerequisites

- Raspberry Pi OS **Bookworm** (64-bit recommended)
- Raspberry Pi Camera Module (v2, v3, or HQ) connected and enabled
- `libcamera` installed and working — verify with:

```bash
rpicam-hello
```

If that shows a preview, your camera stack is healthy. If not, check your camera cable and ensure the camera interface is enabled in `raspi-config`.

---

## Project Structure

```
terra_hawk/
├── mediamtx/
│   ├── mediamtx          # binary
│   └── mediamtx.yml      # configuration
├── main.py               # FastAPI backend
├── start.sh              # startup script
└── mediamtx.log          # generated at runtime (gitignored)
```

---

## Installation

Download the latest release from the [MediaMTX releases page](https://github.com/bluenviron/mediamtx/releases). For Raspberry Pi OS 64-bit, pick the `linux_arm64` `.tar.gz` file.

```bash
mkdir -p mediamtx
cd mediamtx
wget https://github.com/bluenviron/mediamtx/releases/latest/download/mediamtx_vX.X.X_linux_arm64.tar.gz
tar -xzf mediamtx_vX.X.X_linux_arm64.tar.gz
chmod +x mediamtx
```

> Replace `vX.X.X` with the actual version number.

---

## Configuration (`mediamtx/mediamtx.yml`)

The key setting that enables native camera capture is `source: rpiCamera` under `paths`. MediaMTX will control the camera directly via libcamera without needing any external process.

```yaml
paths:
  stream:
    source: rpiCamera
    rpiCameraWidth: 640
    rpiCameraHeight: 640
    rpiCameraFPS: 15
```

### Useful optional settings

| Setting | Description |
|---|---|
| `rpiCameraWidth` / `rpiCameraHeight` | Frame resolution |
| `rpiCameraFPS` | Frames per second |
| `rpiCameraHFlip` / `rpiCameraVFlip` | Flip the image |
| `rpiCameraBitrate` | Encoding bitrate in bits/s (default: 5000000) |
| `rpiCameraAfMode` | Autofocus mode: `auto`, `manual`, `continuous` |
| `sourceOnDemand: true` | Only activate the camera when a client is connected |

Consult the full `mediamtx.yml` for all available `rpiCamera*` options.

---

## Stream URLs

Once running, the stream is available on the following endpoints (replace `localhost` with the Pi's IP for remote access):

| Protocol | URL |
|---|---|
| RTSP | `rtsp://localhost:8554/stream` |
| WebRTC (browser) | `http://localhost:8889/stream` |
| HLS | `http://localhost:8888/stream` |

The Python backend reads from the RTSP endpoint locally:

```python
cap = cv2.VideoCapture("rtsp://localhost:8554/stream")
```

---

## Running

Use the provided `start.sh` script to start both MediaMTX and the FastAPI backend together:

```bash
chmod +x start.sh   # first time only
./start.sh
```

This will:
1. Start `mediamtx` in the background using the config in `mediamtx/mediamtx.yml`
2. Log mediamtx output to `mediamtx.log`
3. Start `uvicorn` in the foreground with `--reload`
4. Kill mediamtx cleanly when you press `Ctrl+C`

---

## Troubleshooting

**`path 'stream' is not configured`**
MediaMTX is running but ignoring the config file. Make sure the config path is passed explicitly to the binary (handled in `start.sh`).

**`ERR [RPI Camera source] process exited unexpectedly`**
libcamera is not installed or not working. Run `rpicam-hello` to diagnose. On Bookworm, `libcamera0.2` should be present — check with:
```bash
apt-cache policy libcamera0.2
```

**`WAR configuration file not found`**
The binary is not receiving the config path argument. Check `start.sh` contains:
```bash
"$MEDIAMTX" "$MEDIAMTX_CONF" >"$MEDIAMTX_LOG" 2>&1 &
```

**Stream connects but immediately drops**
Check `mediamtx.log` for the specific error. Common causes are resolution/FPS combinations the camera module doesn't support, or a bad camera cable.

---

## References

- [Raspberry Pi — Streaming with MediaMTX](https://www.raspberrypi.com/documentation/computers/camera_software.html#streaming-with-mediamtx)
- [MediaMTX GitHub](https://github.com/bluenviron/mediamtx)
- [MediaMTX Docs — Raspberry Pi Cameras](https://mediamtx.org/docs/usage/publish/raspberry-pi-cameras)