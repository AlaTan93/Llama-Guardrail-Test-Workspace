#!/usr/bin/env bash
# Build the frontend entirely inside a pinned Docker container.
# Produces frontend/dist on the host; the host needs only Docker.
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="node:24.16.0-alpine3.22"
UID_G="$(id -u):$(id -g)"

if [ ! -f frontend/package-lock.json ]; then
  echo "No package-lock.json — generating (then freeze versions!)"
  docker run --rm -v "$PWD/frontend:/app" -w /app --user "$UID_G" \
    "$IMAGE" sh -c "npm install --no-audit --no-fund"
fi

docker run --rm -v "$PWD/frontend:/app" -w /app --user "$UID_G" \
  "$IMAGE" sh -c "npm ci --no-audit --no-fund && npm run build"

echo "Built: frontend/dist/index.html"
