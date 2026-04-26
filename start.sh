#!/usr/bin/env bash
set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIAMTX="$SCRIPT_DIR/mediamtx/mediamtx"
MEDIAMTX_CONF="$SCRIPT_DIR/mediamtx/mediamtx.yml"
MEDIAMTX_LOG="$SCRIPT_DIR//mediamtx/mediamtx.log"

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
cleanup() {
  echo ""
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
sleep 1

# ── Start uvicorn in foreground ──────────────────────────────────────────────
echo "[INFO] Starting uvicorn..."
cd "$SCRIPT_DIR"
uv run uvicorn main:app --reload