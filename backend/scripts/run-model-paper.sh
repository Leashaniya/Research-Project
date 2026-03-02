#!/usr/bin/env bash
# Run Model Paper Generation service with a venv (no Docker).
# Usage: from backend/ run: ./scripts/run-model-paper.sh

set -e
SERVICE_ROOT="$(cd "$(dirname "$0")/../services/model-paper-generation" && pwd)"
cd "$SERVICE_ROOT"

VENV_DIR="${SERVICE_ROOT}/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating venv at $VENV_DIR ..."
  python3 -m venv "$VENV_DIR"
fi
source "${VENV_DIR}/bin/activate"

echo "Installing/updating dependencies from requirements.txt ..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Optional: symlink app/data -> data if data lives under app/data
if [[ ! -d "${SERVICE_ROOT}/data" ]] && [[ -d "${SERVICE_ROOT}/app/data" ]]; then
  echo "Linking app/data -> data for local run ..."
  ln -sf app/data data
fi

PORT="${PORT:-8001}"
echo "Starting Model Paper Generation on port $PORT ..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
