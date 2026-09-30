# syntax=docker/dockerfile:1.7
# 多阶段构建：builder 装 uv 跑 sync，runtime 只拷 .venv + 必需源码
# 一个镜像复用：API 和 Worker 共用，靠 entrypoint/command 区分角色

# ===== Builder 阶段 =====
# 指定 linux/amd64，让 Windows 开发机 buildx 也能产出 EC2 可用的镜像
FROM --platform=linux/amd64 python:3.14-slim AS builder

# uv 官方推荐：拷贝独立二进制到 /usr/local/bin
# 用 --mount 方式挂 cache，避免每次重装依赖都重下
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# uv 工作目录约定，与 runtime 保持一致避免路径变动
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# 先只拷依赖清单，利用 docker layer 缓存
# pyproject.toml + uv.lock 改动才会触发 sync 重跑
COPY pyproject.toml uv.lock ./

# --frozen：严格按 uv.lock 装，不解析；--no-dev：不装 dev 组
# 出来的 /opt/venv 是独立环境，下一步直接拷
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ===== Runtime 阶段 =====
FROM --platform=linux/amd64 python:3.14-slim

# 运行时变量：日志不卡缓冲（loguru/uvicorn print 立即可见）
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}"

# 时区设为 Asia/Shanghai，日志时间戳与本地一致
# ca-certificates：httpx 调外部 API 需要
# curl：compose healthcheck 用
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tzdata \
    && ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 非特权用户跑应用，避免容器内以 root 写文件
RUN groupadd -r app && useradd -r -g app -m -d /home/app app

WORKDIR /app

# 从 builder 拷贝 venv
COPY --from=builder /opt/venv /opt/venv

# 拷贝源码、Alembic 配置
COPY --chown=app:app app ./app
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app pyproject.toml ./

# 创建数据/日志目录，挂 volume 用
RUN mkdir -p /app/data/uploads /app/logs \
    && chown -R app:app /app/data /app/logs

USER app

# 默认启动 API；Worker 在 compose 里用 command: arq ... 覆盖
# --host 0.0.0.0：容器内必须监听非回环，否则 nginx/外部访问不到
# --workers 1：单进程模型，并发靠 async；多进程会重复连 Redis/DB 资源
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
