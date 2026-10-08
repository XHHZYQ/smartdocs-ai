# 多阶段构建：builder 用 uv 装依赖，runtime 只保留 venv + 源码
# 一个镜像两种角色：默认跑 API，Worker 由 compose 用 command 覆盖成 arq

# ===== Builder =====
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# UV_PROJECT_ENVIRONMENT：把 venv 建到固定目录，runtime 阶段直接整个拷走
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# 只拷依赖清单，改代码不会让这一层缓存失效
COPY pyproject.toml uv.lock ./

# --frozen：严格按 uv.lock 装，不重新解析
# --no-dev：不装 pytest/ruff 等开发依赖
# --no-install-project：本项目不打 wheel，靠 PYTHONPATH 直接跑源码
RUN uv sync --frozen --no-dev --no-install-project

# ===== Runtime =====
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:${PATH}"

# curl：给 healthcheck 用；ca-certificates：httpx 调外部 API 需要
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r app && useradd -r -g app -m -d /home/app app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# app 目录整体拷贝，包含 migrations/、tasks/、cli.py
COPY --chown=app:app app ./app
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app pyproject.toml ./

RUN mkdir -p /app/data/uploads /app/logs \
    && chown -R app:app /app/data /app/logs

USER app

EXPOSE 8000

# 只探活不查库：DB 挂了不该让容器被判定为 unhealthy 而无限重启
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
