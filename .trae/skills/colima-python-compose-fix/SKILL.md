---
name: "colima-python-compose-fix"
description: "Troubleshoots multi-stage Python/uv Docker builds and docker compose startup failures on colima without buildx. Invoke when 'docker compose up -d --build' or 'make up' fails in this project."
---

# Colima 上 Python/uv 多阶段构建与 Compose 启动排障

适用范围：SmartDocs AI（FastAPI + uv + SQLModel + pgvector），在 **colima 虚拟机缺少 buildx 插件**的环境下执行 `docker compose up -d --build` / `make up` 报错。

## 背景判断

若日志中同时出现以下特征，即命中本场景：

```
WARN Docker Compose requires buildx plugin to be installed
Step 1/19 : FROM ...          ← 经典构建器输出（BuildKit 是 => 风格）
```

colima 默认不带 buildx 时，compose 回退**经典构建器**，不支持 BuildKit 专属语法。注意：「容器 unhealthy」未必是健康检查问题，可能是**应用启动即崩溃**，必须先看容器日志。

## 连锁根因与修复（按出现顺序）

### 1. `env file .env.docker not found`

compose 中 `env_file: .env.docker` 引用的文件被 gitignore，换机后不存在。

- 创建 `.env.docker`，只放密钥类配置（`EMBEDDING_API_KEY`、`JWT_SECRET_KEY`）
- `DATABASE_URL` / `REDIS_URL` / `DEBUG` 等由 compose 的 `environment:` 覆盖（容器间用 service name，不用 localhost）

### 2. `the --mount option requires BuildKit`

修改 `Dockerfile`，移除经典构建器不支持的语法：

- 删除首行 `# syntax=docker/dockerfile:1.7`
- `RUN --mount=type=cache,...` → 普通 `RUN`
- `FROM --platform=linux/amd64` → 不带 platform 的 `FROM`（平台在构建时决定：CI 用 buildx `--platform linux/amd64`；本地 M 芯片原生 arm64；EC2 原生 amd64）

CI 不受影响：`.github/workflows/ci.yml` 用 `docker/setup-buildx-action` + 显式 `platforms: linux/amd64`。

### 3. `OSError: Readme file does not exist: README.md`（uv sync 阶段）

`uv sync` 默认把**本项目自身打 wheel 安装**，而 builder 阶段只拷了 `pyproject.toml` + `uv.lock`，缺少 README.md 与 `app/` 源码。

修复（uv 官方 Docker 指南模式）：

```dockerfile
RUN uv sync --frozen --no-dev --no-install-project
```

runtime 阶段补环境变量，让 `import app` 找到源码：

```dockerfile
ENV PYTHONPATH=/app
```

同时保留：`PYTHONUNBUFFERED=1`（Python stdout 在容器内全缓冲，不设会导致日志延迟/丢失）、非 root 用户。

### 4. `container ... is unhealthy`，实为应用启动崩溃

先看日志再下结论：

```bash
docker logs smartdocs-api 2>&1 | tail -30
docker inspect smartdocs-api --format '{{range .State.Health.Log}}{{.Output}}{{end}}'
```

典型根因：

```
fastapi.exceptions.FastAPIError: Invalid args for response field!
Hint: check that starlette.responses.JSONResponse | dict is a valid Pydantic field type.
```

FastAPI 从返回类型注解推导响应模型；**Response 子类（JSONResponse 等）与 dict 的联合类型无法生成 Pydantic 字段**，新版 FastAPI 启动即抛错。修复：

```python
@router.get("/readiness", response_model=None)
async def readiness() -> JSONResponse | dict:
    ...
```

固定模式：**返回联合类型中出现 Response 子类时，装饰器加 `response_model=None`**。

## 避免经典构建器重复构建

api 和 worker 共用一个镜像（worker 只覆盖 `command`）。经典构建器下两个服务各自 `build:` 会构建两遍。做法：

```yaml
api:
  build: { context: ., dockerfile: Dockerfile }
  image: smartdocs-ai:local      # 构建产物打本地 tag
worker:
  image: smartdocs-ai:local      # 只复用镜像，不重复 build
  command: ["arq", "app.tasks.worker.WorkerSettings"]
```

## 修复后验证

```bash
make up
docker compose ps                              # 5 服务全 Up，api (healthy)
curl http://localhost/health                   # {"status":"ok"}
curl http://localhost/readiness                # {"status":"ok","checks":{"db":"ok","redis":"ok"}}
```

测试库复用 compose 的 postgres（宿主 5433）：

```bash
docker exec smartdocs-postgres psql -U smartdocs -d smartdocsdb \
  -c "CREATE DATABASE smartdocs_test;"
docker exec smartdocs-postgres psql -U smartdocs -d smartdocs_test \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
.venv/bin/python -m pytest -q                   # 期望 75 passed
```

## 排查原则

1. **先看容器日志，不要只看 unhealthy 状态**——崩溃与探活失败是两类问题
2. **按报错出现顺序逐个修**，这些根因是连锁暴露的（前一个挡住后一个）
3. 安装类操作（colima 插件、镜像）只提供命令，不自动执行
4. 健康检查端点不依赖 `Depends`，直接用全局 engine / redis 单例 + try/except，避免被统一异常处理器兜成 500
