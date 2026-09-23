import uvicorn
from arq import run_worker

from app.tasks.worker import WorkerSettings


def dev():
    uvicorn.run("app.main:app", reload=True)


def worker():
    # arq worker 是消费 Redis 的后台进程，不是 ASGI 应用，不能交给 uvicorn
    # run_worker 会阻塞当前进程直到收到终止信号（Ctrl+C）
    run_worker(WorkerSettings)
