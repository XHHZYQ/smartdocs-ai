# === 本地开发 ===
dev:
	uv run uvicorn app.main:app --reload

# arq worker，独立终端运行；文件变化自动重启
# 注意：arq 自带的 --watch 依赖 SIGUSR1，Windows 没有该信号会报 AttributeError，
# 所以用 watchfiles CLI 包住（杀进程重启，跨平台）
worker:
	uv run watchfiles --filter python "uv run arq app.tasks.worker.WorkerSettings" app

lint:
	uv run ruff check .

format:
	uv run ruff format .

# === Docker compose 一键起（5 服务） ===
# 启动顺序由 healthcheck + depends_on 自动编排：
# postgres/redis → api → nginx
up:
	docker compose up -d --build

# 只起依赖（postgres/redis），不开 API/Worker/nginx，方便本地 uv run dev 调试
up-deps:
	docker compose up -d postgres redis

# 停全部（保留 volume）
down:
	docker compose down

# 停并删 volume（慎用：会丢数据库/上传文件数据）
down-v:
	docker compose down -v

# 看实时日志（全部服务）
logs:
	docker compose logs -f --tail=100

# 看某服务日志，用法：make log-svc svc=api
log-svc:
	docker compose logs -f --tail=200 $(svc)

# 容器状态
ps:
	docker compose ps

# === Alembic 迁移（容器内执行，避免本地 Python 版本不一致） ===
# 应用未启动时也能跑：直接用 compose run 起一次性 api 容器
migrate:
	docker compose run --rm api alembic upgrade head

# 生成新迁移脚本：make mig msg="add xxx table"
mig:
	uv run alembic revision --autogenerate -m "$(msg)"

# === 维护 ===
# 进 postgres psql 终端
psql:
	docker compose exec postgres psql -U smartdocs -d smartdocsdb

# 进 redis-cli 终端
redis-cli:
	docker compose exec redis redis-cli

# 清理所有 volume + 镜像（删库重置，慎用）
clean:
	docker compose down -v --rmi local
