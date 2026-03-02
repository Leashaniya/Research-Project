#!/usr/bin/env bash
# Run Academic Guidance service with a venv (no Docker).
# Usage: from backend/ run: ./scripts/run-academic-guidance.sh

set -e
SERVICE_ROOT="$(cd "$(dirname "$0")/../services/academic-guidance" && pwd)"
cd "$SERVICE_ROOT"

VENV_DIR="${SERVICE_ROOT}/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating venv at $VENV_DIR ..."
  python3 -m venv "$VENV_DIR"
fi
source "${VENV_DIR}/bin/activate"

echo "Installing/updating dependencies from pyproject.toml ..."
pip install -q --upgrade pip
pip install -q -e .

PORT="${PORT:-8000}"
echo "Starting Academic Guidance on port $PORT ..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
