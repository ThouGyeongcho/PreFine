FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    TZ=Asia/Shanghai

WORKDIR /app

RUN groupadd --system finance-toolkit \
    && useradd --system --gid finance-toolkit --home-dir /app finance-toolkit \
    && mkdir -p /data \
    && chown finance-toolkit:finance-toolkit /data

COPY pyproject.toml ./
COPY backend/ backend/
RUN python -m pip install --no-cache-dir .

COPY --from=frontend-builder /build/frontend/dist frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/finance-toolkit-entrypoint
RUN sed -i 's/\r$//' /usr/local/bin/finance-toolkit-entrypoint \
    && chmod 0555 /usr/local/bin/finance-toolkit-entrypoint

USER finance-toolkit
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"]

ENTRYPOINT ["finance-toolkit-entrypoint"]
