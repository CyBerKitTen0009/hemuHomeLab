FROM node:24-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run check && npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_CACHE_DIR=/tmp/uv-cache
COPY pyproject.toml uv.lock LICENSE ./
RUN uv sync --frozen --no-dev && groupadd --gid 10001 hcc && useradd --uid 10001 --gid 10001 --no-create-home hcc
COPY backend/ backend/
COPY --from=frontend /build/build /app/frontend/build
RUN mkdir -p /data /run/hcc && chown -R 10001:10001 /data /app
USER 10001:10001
EXPOSE 8000
CMD [".venv/bin/uvicorn", "backend.hcc.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
