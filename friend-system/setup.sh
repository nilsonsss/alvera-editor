#!/usr/bin/env bash
# Installs everything the system needs. Safe to run again: it only adds what is missing.
#   bash setup.sh           install
#   bash setup.sh --check   say whether it is ready (nothing is changed)
set -uo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"; TOOLS="$ROOT/tools/bin"; VENV="$HOME/.cache/video-editor/whisperx-venv"; PY="$VENV/bin/python"
export PATH="$TOOLS:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

ffmpeg_ok() { command -v ffmpeg >/dev/null && command -v ffprobe >/dev/null && [ "$(ffmpeg -version | head -1 | sed -E 's/ffmpeg version n?([0-9]+).*/\1/')" -ge 7 ] 2>/dev/null; }
node_ok() { command -v node >/dev/null && [ "$(node -v | sed -E 's/v([0-9]+).*/\1/')" -ge 20 ] 2>/dev/null; }
missing() {
  ffmpeg_ok || echo "ffmpeg"
  node_ok || echo "node"
  { [ -x "$PY" ] && "$PY" -c "import whisperx, torchvision" 2>/dev/null; } || echo "speech-tools"
  [ -d projects/_remotion/node_modules/remotion ] || echo "graphics-tools"
  [ -f "$HOME/.cache/video-editor/.models_ready" ] || echo "models"
}
if [ "${1:-}" = "--check" ]; then
  m="$(missing | tr '\n' ' ')"
  if [ -z "$m" ]; then echo "VIDEO EDITING SYSTEM: READY"; else echo "VIDEO EDITING SYSTEM: NOT INSTALLED YET (missing: $m). Run: bash setup.sh"; fi
  exit 0
fi

set -e
if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "Automatic install covers Apple Silicon Macs. On this computer install ffmpeg 7+, Node 20+ and uv yourself, then run this again."
  ffmpeg_ok && node_ok || exit 1
fi
mkdir -p "$TOOLS"
if ! ffmpeg_ok; then
  echo "== installing ffmpeg"
  if command -v brew >/dev/null; then
    brew install ffmpeg
  else
    T="$(mktemp -d)"
    for b in ffmpeg ffprobe; do
      curl -fsSL "https://www.osxexperts.net/${b}80arm.zip" -o "$T/$b.zip"; unzip -qo "$T/$b.zip" -d "$T"; mv "$T/$b" "$TOOLS/$b"; chmod +x "$TOOLS/$b"; xattr -d com.apple.quarantine "$TOOLS/$b" 2>/dev/null || true
    done
  fi
fi
if ! node_ok; then
  echo "== installing Node"
  if command -v brew >/dev/null; then
    brew install node
  else
    V=v22.14.0; curl -fsSL "https://nodejs.org/dist/$V/node-$V-darwin-arm64.tar.gz" | tar -xz -C "$ROOT/tools"
    for b in node npm npx; do ln -sf "../node-$V-darwin-arm64/bin/$b" "$TOOLS/$b"; done
  fi
fi
if ! command -v uv >/dev/null; then
  echo "== installing uv"
  if command -v brew >/dev/null; then brew install uv; else curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 sh >/dev/null; fi
fi
echo "== installing the speech and picture tools (a few minutes)"
mkdir -p "$(dirname "$VENV")"
[ -x "$PY" ] || uv venv "$VENV" --python 3.11 -q
uv pip install -q --python "$PY" "whisperx==3.8.6"
echo "== installing the graphics tools"
(cd projects/_remotion && npm install --silent --no-fund --no-audit && npx remotion browser ensure >/dev/null)
echo "== downloading the speech and picture models (about 5 GB, once)"
"$PY" - <<'PY'
import numpy as np, whisperx
from torchvision.models.segmentation import deeplabv3_resnet101, DeepLabV3_ResNet101_Weights
deeplabv3_resnet101(weights=DeepLabV3_ResNet101_Weights.COCO_WITH_VOC_LABELS_V1)
for name in ("large-v3", "medium.en"):
    whisperx.load_model(name, "cpu", compute_type="int8", language="en").transcribe(np.zeros(16000, np.float32), batch_size=1)
whisperx.load_align_model(language_code="en", device="cpu")
print("models ok")
PY
touch "$HOME/.cache/video-editor/.models_ready"
bash "$ROOT/setup.sh" --check
