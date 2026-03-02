#!/usr/bin/env bash
# Run local gateway (no Docker). Proxies /guidance -> :8000, /papers -> :8001.
# Usage: from backend/ run: ./scripts/run-gateway.sh

set -e
GATEWAY_ROOT="$(cd "$(dirname "$0")/../gateway-local" && pwd)"
cd "$GATEWAY_ROOT"

VENV_DIR="${GATEWAY_ROOT}/.venv"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating venv at $VENV_DIR ..."
  python3 -m venv "$VENV_DIR"
fi
source "${VENV_DIR}/bin/activate"

echo "Installing gateway dependencies ..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

PORT="${PORT:-80}"
echo "Starting gateway on port $PORT (guidance -> 8000, papers -> 8001) ..."
exec python -m uvicorn main:app --host 0.0.0.0 --port "$PORT"
