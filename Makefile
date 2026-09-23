dev:
	uv run uvicorn app.main:app --reload

# arq worker，独立终端运行；--watch 改任务代码自动重启
worker:
	uv run arq app.tasks.worker.WorkerSettings --watch

lint:
	uv run ruff check .

format:
	uv run ruff format .