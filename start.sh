#!/usr/bin/env bash
set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIAMTX="$SCRIPT_DIR/mediamtx/mediamtx"
MEDIAMTX_CONF="$SCRIPT_DIR/mediamtx/mediamtx.yml"
MEDIAMTX_LOG="$SCRIPT_DIR/mediamtx/mediamtx.log"
FFMPEG_LOG="$SCRIPT_DIR/mediamtx/ffmpeg-esp32.log"

# ── ESP32 camera config ─────────────────────────────────────────────────────
ESP32_RTSP="rtsp://192.168.178.59:554/stream"
ESP32_MEDIAMTX_PATH="rtsp://localhost:8554/esp32-cam"

# ── Kill orphaned processes from previous runs ──────────────────────────────
echo "[INFO] Cleaning up orphaned processes..."
pkill -f "mediamtx.*mediamtx.yml" 2>/dev/null && echo "[INFO] Killed orphaned mediamtx" || true
pkill -f "ffmpeg.*esp32-cam" 2>/dev/null && echo "[INFO] Killed orphaned ffmpeg (esp32)" || true
pkill -f "mtxrpicam" 2>/dev/null && echo "[INFO] Killed orphaned mtxrpicam" || true
pkill -f "uvicorn main:app" 2>/dev/null && echo "[INFO] Killed orphaned uvicorn" || true
sleep 1

# ── Sanity checks ────────────────────────────────────────────────────────────
if [[ ! -x "$MEDIAMTX" ]]; then
  echo "[ERROR] mediamtx binary not found or not executable: $MEDIAMTX"
  exit 1
fi

if [[ ! -f "$MEDIAMTX_CONF" ]]; then
  echo "[ERROR] mediamtx config not found: $MEDIAMTX_CONF"
  exit 1
fi

if ! command -v uv &>/dev/null; then
  echo "[ERROR] uv is not installed or not on PATH"
  exit 1
fi

# ── Cleanup on exit (Ctrl+C or error) ───────────────────────────────────────
FFMPEG_PID=""
cleanup() {
  echo ""
  if [[ -n "$FFMPEG_PID" ]]; then
    echo "[INFO] Shutting down ffmpeg transcode (PID $FFMPEG_PID)..."
    kill "$FFMPEG_PID" 2>/dev/null || true
    wait "$FFMPEG_PID" 2>/dev/null || true
  fi
  echo "[INFO] Shutting down mediamtx (PID $MEDIAMTX_PID)..."
  kill "$MEDIAMTX_PID" 2>/dev/null || true
  wait "$MEDIAMTX_PID" 2>/dev/null || true
  echo "[INFO] Done."
}
trap cleanup EXIT

# ── Start mediamtx in background ────────────────────────────────────────────
echo "[INFO] Starting mediamtx... (logs → $MEDIAMTX_LOG)"
"$MEDIAMTX" "$MEDIAMTX_CONF" >"$MEDIAMTX_LOG" 2>&1 &
MEDIAMTX_PID=$!
echo "[INFO] mediamtx running with PID $MEDIAMTX_PID"

# Give mediamtx a moment to initialize
sleep 2

# ── Start ffmpeg ESP32 MJPEG→H.264 transcode ────────────────────────────────
echo "[INFO] Starting ffmpeg transcode: ESP32 MJPEG → H.264..."
ffmpeg -hide_banner -loglevel warning \
  -rtsp_transport tcp \
  -i "$ESP32_RTSP" \
  -c:v libx264 -preset ultrafast -tune zerolatency \
  -b:v 800k -maxrate 1M -bufsize 500k \
  -g 30 -keyint_min 15 \
  -f rtsp -rtsp_transport tcp \
  "$ESP32_MEDIAMTX_PATH" \
  >"$FFMPEG_LOG" 2>&1 &
FFMPEG_PID=$!
echo "[INFO] ffmpeg transcode running with PID $FFMPEG_PID"

sleep 1

# ── Start uvicorn in foreground ──────────────────────────────────────────────
echo "[INFO] Starting uvicorn..."
cd "$SCRIPT_DIR"
uv run uvicorn main:app --reload --host 0.0.0.0
