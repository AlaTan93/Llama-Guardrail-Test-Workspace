# ---- stage 1: SPA build (pinned node; host needs only Docker) ----
FROM node:24.16.0-alpine3.22 AS spa
WORKDIR /spa
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
# types are generated from the committed openapi.json (exported from the harness)
RUN npm run gen:api && npm run build

# ---- stage 2: harness runtime ----
FROM python:3.13-slim
WORKDIR /app
COPY harness/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY harness/app ./app
COPY --from=spa /spa/dist ./static
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
