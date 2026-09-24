"""arq worker 入口。

启动（项目根目录，独立终端）：
    uv run arq app.tasks.worker.WorkerSettings --watch
"""

from arq.connections import RedisSettings

import app.models  # noqa: F401  # 注册所有表到 SQLModel.metadata，避免 worker 独立进程里外键解析报 NoReferencedTableError
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.redis import close_redis, init_redis
from app.tasks.document_jobs import process_document_file


async def on_startup(ctx: dict) -> None:
    # worker 是独立进程，不跑 FastAPI lifespan：
    # 日志、Redis（任务里失效列表缓存用）在这里自行初始化
    setup_logging()
    await init_redis()


async def on_shutdown(ctx: dict) -> None:
    await close_redis()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.arq_redis_url)
    functions = [process_document_file]
    on_startup = on_startup
    on_shutdown = on_shutdown
    max_jobs = settings.arq_max_jobs  # 单 worker 并发 job 数
    job_timeout = settings.arq_job_timeout_seconds
    max_tries = settings.arq_max_tries  # 最多尝试次数
    keep_result = 0  # 不保留 arq result，任务状态以 DB 为准，省 Redis
