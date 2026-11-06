#!/usr/bin/env bash
# Build the persistent WhisperX environment. Run once, ever.
# Reused by every job; lives outside the project so it survives folder moves.
set -euo pipefail

UV="${UV:-$HOME/.local/bin/uv}"
command -v uv >/dev/null 2>&1 && UV=uv

VENV="$HOME/.cache/video-editor/whisperx-venv"
PY="$VENV/bin/python"

if [ -x "$PY" ]; then
  echo "whisperx venv already exists: $VENV"
else
  mkdir -p "$(dirname "$VENV")"
  "$UV" venv "$VENV" --python 3.11
fi

"$UV" pip install --python "$PY" "whisperx==3.8.6"

echo
"$PY" -c "import whisperx, torch; print('whisperx OK  torch', torch.__version__)"
echo "venv python: $PY"
