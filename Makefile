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