# Red-team dashboard image — everything pinned for reproducibility.
#
#   stage 1: build the SPA in the pinned node image (no host node/npm needed)
#   stage 2: python runtime + frozen deps from uv.lock + built SPA + docker CLI
#            (the CLI lets the job manager start/stop llama.cpp containers via
#            the mounted docker socket)

########## Stage 1: SPA ##########
FROM node:24.16.0-alpine3.22 AS frontend
WORKDIR /app
ENV npm_config_cache=/tmp/.npm
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

########## Stage 2: runtime ##########
FROM python:3.13-slim-bookworm@sha256:c45a22ea000adfd9cda29364bbe7edd23001ce5cc2ad15857cfbf7766943b9ca

# Static docker CLI, version-matched to the host daemon (29.7.2)
ADD https://download.docker.com/linux/static/stable/x86_64/docker-29.7.2.tgz /tmp/
RUN tar -xzf /tmp/docker-29.7.2.tgz -C /tmp \
    && mv /tmp/docker/docker /usr/local/bin/docker \
    && rm -rf /tmp/docker* \
    && docker --version

# uv, pinned by digest
COPY --from=ghcr.io/astral-sh/uv@sha256:88bc6eb1ccd4b82efd0e1b530caffabddf50dc2bf612e66c14ea25b8ee8a4d3d /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# Dependencies first (cacheable layer, frozen by uv.lock)
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# Application code
COPY src/ ./src/
COPY main.py make_tables.py merge_runs.py ./
COPY README.md ./

# Built SPA from stage 1
COPY --from=frontend /app/dist ./frontend/dist

EXPOSE 8000
CMD ["python", "-m", "src.web", "--host", "0.0.0.0", "--port", "8000"]
