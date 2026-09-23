"""文档处理 ETL 任务。

流水线（对照原 upload 接口里的同步逻辑，搬到独立 worker 进程）：
  processing → 幂等清理旧产物 → 读原始文件 → extract/clean
  → 建 Document → chunk → embedding(分批) → 写 Chunks → success

错误分类：
  - 外部依赖抖动（embedding 超时/网络错误/5xx）→ Retry，指数退避，最多 arq_max_tries 次
  - 数据本身问题（空文本、PDF 损坏、磁盘文件丢失）→ 直接 failed
"""

from datetime import timedelta

import httpx
from arq import Retry
from arq.worker import func
from loguru import logger
from sqlalchemy import delete
from starlette.concurrency import run_in_threadpool

from app.core.cache import cache_delete_pattern
from app.core.config import settings
from app.core.db import new_session
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_file import DocumentFile, ExtractionStatus
from app.services.chunking import chunk_text
from app.services.embedding import get_embeddings
from app.services.extraction import clean_text, extract_text
from app.services.storage import read_file

# 指数退避表（秒）：第 1 次失败等 5s，第 2 次等 30s
_RETRY_DELAYS = (5, 30)


@func
async def process_document_file(ctx: dict, doc_file_id: int) -> None:
    job_try: int = ctx.get("job_try", 1)

    async with new_session() as session:
        doc_file = await session.get(DocumentFile, doc_file_id)
        if doc_file is None:
            # 防御：记录已被删除（worker 与 API 是不同进程，删除无联动），安全退出
            logger.warning("doc_file {} 不存在，任务安全退出", doc_file_id)
            return

        # commit 后对象会 expire，之后读属性会触发 lazy load 报错，需要的标量全部提前取
        source_type = doc_file.source_type
        owner_id = doc_file.owner_id
        tenant_id = doc_file.tenant_id
        original_filename = doc_file.original_filename
        old_document_id = doc_file.document_id

        # ---------- 翻转 processing（含每一轮重试），并失效列表缓存 ----------
        doc_file.extraction_status = ExtractionStatus.PROCESSING
        session.add(doc_file)
        await session.commit()
        await cache_delete_pattern(f"docfiles:list:tenant={tenant_id}:*")

        try:
            # ---------- 幂等：重跑前清掉上一轮产物，保证不产生重复 Document ----------
            if old_document_id is not None:
                await session.exec(
                    delete(Chunk).where(Chunk.document_id == old_document_id)
                )
                old_doc = await session.get(Document, old_document_id)
                if old_doc is not None:
                    await session.delete(old_doc)
                doc_file.document_id = None
                await session.commit()

            # ---------- 1. 读原始文件 + 文本提取（阻塞 IO，丢线程池） ----------
            raw_bytes = await run_in_threadpool(read_file, doc_file_id)
            raw_text = await run_in_threadpool(extract_text, source_type, raw_bytes)
            cleaned_text = clean_text(raw_text)
            if not cleaned_text:
                raise ValueError("Extracted text is empty")

            # ---------- 2. 建 Document ----------
            document = Document(
                title=original_filename,
                content=cleaned_text,
                owner_id=owner_id,
                tenant_id=tenant_id,
            )
            session.add(document)
            await session.flush()
            await session.refresh(document)
            document_id = document.id

            # ---------- 3. 切块 + 分批向量化 ----------
            chunks = chunk_text(cleaned_text)
            embeddings = await get_embeddings(chunks)

            # ---------- 4. 写 Chunks ----------
            chunk_records = [
                Chunk(
                    tenant_id=tenant_id,
                    document_id=document_id,
                    chunk_index=idx,
                    content=chunk,
                    char_count=len(chunk),
                    embedding=embedding,
                )
                for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings))
            ]
            session.add_all(chunk_records)

            doc_file.document_id = document_id
            doc_file.extraction_status = ExtractionStatus.SUCCESS
            doc_file.error_message = None
            session.add(doc_file)
            await session.commit()

        except Retry:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            await _handle_retryable(session, doc_file_id, job_try, exc)
        except httpx.HTTPStatusError as exc:
            # 5xx 服务端抖动可重试；4xx（key 错误/参数非法等）重试无意义
            if exc.response.status_code >= 500:
                await _handle_retryable(session, doc_file_id, job_try, exc)
            await _mark_failed(session, doc_file_id, exc)
        except Exception as exc:
            # ValueError/FileNotFoundError/PDF 解析错误等：数据问题，不重试
            await _mark_failed(session, doc_file_id, exc)

        await cache_delete_pattern(f"docfiles:list:tenant={tenant_id}:*")


async def _handle_retryable(
    session, doc_file_id: int, job_try: int, exc: Exception
) -> None:
    """可重试错误：未达上限则 rollback 后抛 Retry（arq 把 job 置 deferred，到点重跑）。"""
    max_tries = settings.arq_max_tries

    if job_try >= max_tries:
        logger.error(
            "doc_file {} 已尝试 {} 次仍失败，落 failed", doc_file_id, max_tries
        )
        await _mark_failed(session, doc_file_id, exc, retry_exhausted=True)
        return

    await session.rollback()
    delay = _RETRY_DELAYS[min(job_try - 1, len(_RETRY_DELAYS) - 1)]
    logger.warning(
        "doc_file {} 第 {}/{} 次尝试失败，{}s 后重试: {}",
        doc_file_id,
        job_try,
        max_tries,
        delay,
        exc,
    )
    raise Retry(defer=timedelta(seconds=delay)) from exc


async def _mark_failed(
    session, doc_file_id: int, exc: Exception, retry_exhausted: bool = False
) -> None:
    """落 failed。先 rollback 清掉半成品事务（如已 flush 的 Document），再重新取记录。"""
    await session.rollback()
    doc_file = await session.get(DocumentFile, doc_file_id)
    if doc_file is None:
        return

    prefix = "重试次数耗尽: " if retry_exhausted else ""
    doc_file.extraction_status = ExtractionStatus.FAILED
    doc_file.error_message = f"{prefix}{type(exc).__name__}: {exc}"[:500]
    session.add(doc_file)
    await session.commit()
    logger.exception("doc_file {} 处理失败", doc_file_id)
