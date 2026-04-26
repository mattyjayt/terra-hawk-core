#!/usr/bin/env bash
set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$SCRIPT_DIR/mediamtx"
ARCH="linux_arm64"

# ── Resolve latest release tag from GitHub API ───────────────────────────────
echo "[INFO] Fetching latest MediaMTX release..."
LATEST=$(curl -fsSL https://api.github.com/repos/bluenviron/mediamtx/releases/latest \
  | grep '"tag_name"' \
  | sed 's/.*"tag_name": *"\(.*\)".*/\1/')

if [[ -z "$LATEST" ]]; then
  echo "[ERROR] Could not determine latest release. Check your internet connection."
  exit 1
fi

TARBALL="mediamtx_${LATEST}_${ARCH}.tar.gz"
URL="https://github.com/bluenviron/mediamtx/releases/download/${LATEST}/${TARBALL}"

echo "[INFO] Latest version: $LATEST"

# ── Create install directory ─────────────────────────────────────────────────
echo "[INFO] Creating directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# ── Download ─────────────────────────────────────────────────────────────────
echo "[INFO] Downloading $TARBALL..."
curl -fSL "$URL" -o "$INSTALL_DIR/$TARBALL"

# ── Extract ──────────────────────────────────────────────────────────────────
echo "[INFO] Extracting..."
tar -xzf "$INSTALL_DIR/$TARBALL" -C "$INSTALL_DIR"
rm "$INSTALL_DIR/$TARBALL"

# ── Make binary executable ───────────────────────────────────────────────────
chmod +x "$INSTALL_DIR/mediamtx"
echo "[INFO] Binary ready: $INSTALL_DIR/mediamtx"

# ── Backup original yml ──────────────────────────────────────────────────────
echo "[INFO] Backing up original mediamtx.yml → mediamtx.yml.original"
cp "$INSTALL_DIR/mediamtx.yml" "$INSTALL_DIR/mediamtx.yml.original"

# ── Patch paths section ──────────────────────────────────────────────────────
# The original yml ends with a 'paths:' section. We strip everything from
# 'paths:' onward and append our own configured paths block in its place.
echo "[INFO] Patching paths section in mediamtx.yml..."

sed '/^paths:/,$d' "$INSTALL_DIR/mediamtx.yml.original" > "$INSTALL_DIR/mediamtx.yml"

cat >> "$INSTALL_DIR/mediamtx.yml" << 'EOF'
###############################################
# Path settings

paths:
  stream:
    source: rpiCamera
    rpiCameraWidth: 640
    rpiCameraHeight: 640
    rpiCameraFPS: 15

  all_others:
EOF

echo ""
echo "✓ MediaMTX $LATEST installed successfully."
echo ""
echo "  Binary  : $INSTALL_DIR/mediamtx"
echo "  Config  : $INSTALL_DIR/mediamtx.yml         (customized)"
echo "  Original: $INSTALL_DIR/mediamtx.yml.original (reference)"
echo "  Stream  : rtsp://localhost:8554/stream"
echo ""
echo "  Run the stack with: ./start.sh"