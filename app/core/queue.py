"""arq 任务队列连接池。
FastAPI lifespan 里 init / close；业务代码只调用 enqueue_* 函数。
"""

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings
from loguru import logger

from app.core.config import settings

arq_pool: ArqRedis | None = None


async def init_queue() -> None:
    global arq_pool
    arq_pool = await create_pool(RedisSettings.from_dsn(settings.arq_redis_url))
    logger.info("arq queue connected: {}", settings.arq_redis_url)


async def close_queue() -> None:
    global arq_pool
    if arq_pool is not None:
        await arq_pool.aclose()
        arq_pool = None
        logger.info("arq queue connection closed")


async def enqueue_document_job(doc_file_id: int) -> None:
    """入队文档处理任务。

    _job_id 固定为 docfile:{id}：
    - 未完成的同名 job 重复入队时 arq 直接拒绝，天然防重复点击
    - 终态（success/failed）后允许用同一 id 重新入队（手动 retry）
    """
    if arq_pool is None:
        raise RuntimeError("arq pool is not initialized. Check lifespan.")

    await arq_pool.enqueue_job(
        "process_document_file",
        doc_file_id,
        _job_id=f"docfile:{doc_file_id}",
    )


async def enqueue_rebuild_chunks(document_id: int) -> None:
    """入队 document create/update 的切块+向量化任务。

    _job_id 固定为 doc:{id}：
    - 同一文档的未完成 ETL 重复入队时 arq 直接拒绝，防重复点击
    - 终态后允许用同一 id 重新入队（手动重试 / 再次更新触发重建）
    """
    if arq_pool is None:
        raise RuntimeError("arq pool is not initialized. Check lifespan.")

    await arq_pool.enqueue_job(
        "rebuild_document_chunks",
        document_id,
        _job_id=f"doc:{document_id}",
    )
