# MediaMTX — Raspberry Pi Camera Streaming

MediaMTX (formerly `rtsp-simple-server`) is a media server that captures directly from the Raspberry Pi camera module via libcamera and re-streams it over RTSP, WebRTC, HLS, RTMP, and SRT — without needing external tools like `rpicam-vid` or `ffmpeg`.

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
│   ├── mediamtx               # binary
│   ├── mediamtx.yml           # customized configuration
│   └── mediamtx.yml.original  # original config from release (reference)
├── main.py                    # FastAPI backend
├── install.sh                 # one-shot install script
├── start.sh                   # startup script
└── mediamtx.log               # generated at runtime (gitignored)
```

---

## Installation

### Option 1 — Quick install (recommended)

Run the provided install script from the project root. It will automatically fetch the latest MediaMTX release, extract it into `mediamtx/`, make the binary executable, and write a pre-configured `mediamtx.yml` with the `stream` path set up for the Raspberry Pi camera.

```bash
chmod +x install.sh
./install.sh
```

After it completes you'll have:

- `mediamtx/mediamtx` — the binary, ready to run
- `mediamtx/mediamtx.yml` — customized config with the `stream` path
- `mediamtx/mediamtx.yml.original` — untouched original from the release, useful as a reference for all available settings

Then jump straight to [Running](#running).

---

### Option 2 — Manual install

Use this approach if you want full control over the version or configuration, or just want to understand what's happening under the hood.

**1. Download the release**

Go to the [MediaMTX releases page](https://github.com/bluenviron/mediamtx/releases) and pick the `linux_arm64` `.tar.gz` for Raspberry Pi OS 64-bit, or `armv7` for 32-bit.

```bash
mkdir -p mediamtx && cd mediamtx
wget https://github.com/bluenviron/mediamtx/releases/download/vX.X.X/mediamtx_vX.X.X_linux_arm64.tar.gz
tar -xzf mediamtx_vX.X.X_linux_arm64.tar.gz
chmod +x mediamtx
```

> Replace `vX.X.X` with the version you want.

**2. Back up the original config**

The tarball includes a fully documented `mediamtx.yml`. Keep it as a reference before making changes:

```bash
cp mediamtx.yml mediamtx.yml.original
```

**3. Configure the `paths` section**

Open `mediamtx.yml` and scroll to the `paths:` section at the bottom. Replace its contents with your path definition. The key setting is `source: rpiCamera`, which tells MediaMTX to capture directly from the camera via libcamera:

```yaml
paths:
  stream:
    source: rpiCamera
    rpiCameraWidth: 640
    rpiCameraHeight: 640
    rpiCameraFPS: 15

  all_others:
```

Everything above `paths:` in the file (global settings, protocol config, auth, etc.) can be left at its defaults or adjusted as needed. The original `mediamtx.yml.original` documents every available option with inline comments.

**Useful `rpiCamera` settings**

| Setting | Description |
|---|---|
| `rpiCameraWidth` / `rpiCameraHeight` | Frame resolution |
| `rpiCameraFPS` | Frames per second |
| `rpiCameraHFlip` / `rpiCameraVFlip` | Flip the image |
| `rpiCameraBitrate` | Encoding bitrate in bits/s (default: `5000000`) |
| `rpiCameraAfMode` | Autofocus mode: `auto`, `manual`, `continuous` |
| `rpiCameraExposure` | Exposure mode: `normal`, `short`, `long` |
| `sourceOnDemand: true` | Only activate the camera when a client connects |

---

## Stream URLs

Once running, the stream is available on the following endpoints. Replace `localhost` with the Pi's IP address for remote access:

| Protocol | URL |
|---|---|
| RTSP | `rtsp://localhost:8554/stream` |
| WebRTC (browser) | `http://localhost:8889/stream` |
| HLS | `http://localhost:8888/stream` |

The FastAPI backend reads from the RTSP endpoint locally:

```python
cap = cv2.VideoCapture("rtsp://localhost:8554/stream")
```

---

## Running

Use `start.sh` to launch both MediaMTX and the FastAPI backend together:

```bash
chmod +x start.sh   # first time only
./start.sh
```

This will:

1. Start `mediamtx` in the background using `mediamtx/mediamtx.yml`
2. Write mediamtx logs to `mediamtx.log`
3. Start `uvicorn main:app --reload` in the foreground
4. Kill mediamtx cleanly on `Ctrl+C`

---

## Troubleshooting

**`path 'stream' is not configured`**
MediaMTX is running but not reading the config file. Ensure `start.sh` passes the config path explicitly to the binary:
```bash
"$MEDIAMTX" "$MEDIAMTX_CONF" >"$MEDIAMTX_LOG" 2>&1 &
```

**`WAR configuration file not found`**
Same root cause as above — the binary is falling back to looking in the working directory. Check the `MEDIAMTX_CONF` variable in `start.sh` points to `mediamtx/mediamtx.yml`.

**`ERR [RPI Camera source] process exited unexpectedly`**
libcamera is not installed or not functioning. Run `rpicam-hello` to diagnose. On Bookworm, `libcamera0.2` should be present:
```bash
apt-cache policy libcamera0.2
```

**Stream connects but immediately drops**
Check `mediamtx.log` for details. Common causes are an unsupported resolution/FPS combination for your camera module, or a faulty camera cable.

---

## References

- [Raspberry Pi — Streaming with MediaMTX](https://www.raspberrypi.com/documentation/computers/camera_software.html#streaming-with-mediamtx)
- [MediaMTX GitHub](https://github.com/bluenviron/mediamtx)
- [MediaMTX Docs — Raspberry Pi Cameras](https://mediamtx.org/docs/usage/publish/raspberry-pi-cameras)