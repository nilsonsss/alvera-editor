#!/usr/bin/env bash
# Copy a raw clip into a job folder. The original is never moved or modified.
# Usage: intake.sh <path/to/raw.mov> <job-name-in-kebab-case>
set -euo pipefail

SRC="${1:?usage: intake.sh <raw-clip> <job-name>}"
JOB="${2:?usage: intake.sh <raw-clip> <job-name>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/projects/$JOB"

[ -f "$SRC" ] || { echo "no such file: $SRC" >&2; exit 1; }

mkdir -p "$DEST/raw" "$DEST/transcript" "$DEST/graphics" "$DEST/outputs"

BASE="$(basename "$SRC")"
if [ -e "$DEST/raw/$BASE" ]; then
  echo "already in place: $DEST/raw/$BASE"
else
  cp -c -p "$SRC" "$DEST/raw/$BASE" 2>/dev/null || cp -p "$SRC" "$DEST/raw/$BASE"   # APFS clone (instant, ZERO extra disk) when on the same volume, else a real copy; original untouched
  chmod a-w "$DEST/raw/$BASE"           # read-only: the raw is never edited
  echo "copied -> $DEST/raw/$BASE"
fi

echo
echo "--- ffprobe ---"
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_frames \
  -show_entries format=duration,size \
  -of default=noprint_wrappers=1 "$DEST/raw/$BASE"
