#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .

if [[ ! -f config.yaml ]]; then
  cp config.example.yaml config.yaml
  chmod 600 config.yaml
  echo "Utworzono config.yaml. Uzupełnij źródła i dane wyłącznie przez zmienne środowiskowe."
fi

mkdir -p output state
echo "Instalacja zakończona. Test: .venv/bin/kr-live-epg build --config config.yaml"
