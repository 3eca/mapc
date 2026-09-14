FROM node:24-alpine AS frontend-build
WORKDIR /workspace/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.9 AS uv
FROM python:3.12-slim AS python-build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY --from=frontend-build /workspace/src/mapc/static/app/ ./src/mapc/static/app/
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=python-build /app/.venv /app/.venv
RUN mkdir /data
ENV MAPC_HOST=0.0.0.0 MAPC_PORT=8080 MAPC_DATABASE_URL=sqlite:////data/mapc.db
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"]
CMD ["/app/.venv/bin/uvicorn", "mapc.app:app", "--host", "0.0.0.0", "--port", "8080", "--no-proxy-headers"]
