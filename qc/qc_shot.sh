#!/bin/bash
# Run on the GPU / ComfyUI host. CPU only — does not take VRAM from H3.
set -euo pipefail
export CUDA_VISIBLE_DEVICES=""
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ $# -lt 1 ]]; then
  echo "usage: $0 <video.mp4> [shot_id]" >&2
  exit 2
fi
VIDEO="$1"
SHOT="${2:-}"
BOARD="${BOARD:-/root/fanzi-mu/ep01-script-board.json}"
exec "$ROOT/.venv/bin/python" "$ROOT/qc_shot.py" --video "$VIDEO" ${SHOT:+--shot "$SHOT"} --board "$BOARD" --models "$ROOT/models" --expect "$ROOT/expectations.json"
