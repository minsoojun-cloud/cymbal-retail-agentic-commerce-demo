# ---- Stage 1: Build React + TypeScript Frontend ----
FROM node:22-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm install
COPY web/ ./
RUN npm run build

# ---- Stage 2: Python 3.12 FastAPI + Japanese Fonts ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY scripts/ ./scripts/
RUN uv sync --no-dev
COPY --from=web /web/dist ./web/dist
ENV STATIC_DIR=/app/web/dist PORT=8080 LOCAL_STORAGE_DIR=/app/data/banners
CMD ["sh", "-c", "uv run --no-dev uvicorn --factory edion_banner.main:get_app --host 0.0.0.0 --port ${PORT}"]
