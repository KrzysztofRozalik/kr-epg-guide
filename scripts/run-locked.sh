#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${KR_EPG_CONFIG:-$PROJECT_DIR/config.yaml}"
MODE="${1:-live}"

mkdir -p "$PROJECT_DIR/state"
exec flock -n "$PROJECT_DIR/state/build.lock" \
  "$PROJECT_DIR/.venv/bin/kr-live-epg" build --config "$CONFIG_PATH" --mode "$MODE"
