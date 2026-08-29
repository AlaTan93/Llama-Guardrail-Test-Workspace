#!/usr/bin/env bash
# Vite dev server inside a container, proxying /api to the host backend.
# Start the backend first:  uv run uvicorn src.web.app:app --port 8000
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="node:24.16.0-alpine3.22"
UID_G="$(id -u):$(id -g)"

docker run --rm -v "$PWD/frontend:/app" -w /app -p 5173:5173 --user "$UID_G" \
  -e API_TARGET="${API_TARGET:-http://host.docker.internal:8000}" \
  --add-host=host.docker.internal:host-gateway \
  "$IMAGE" sh -c "npm install --no-audit --no-fund >/dev/null 2>&1 || true; npm run dev -- --host 0.0.0.0"
