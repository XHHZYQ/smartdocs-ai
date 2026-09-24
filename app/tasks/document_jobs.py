"""文档处理 ETL 任务。

两条链路共用 build_chunk_records（切块 + 向量化 + 构造 Chunk）：
  - process_document_file：上传文件 → 提取/清洗 → 建 Document → 切块+向量化 → 写 Chunks
  - rebuild_document_chunks：document create/update → 已有 cleaned_text → 切块+向量化 → 写 Chunks

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
from app.services.chunking import build_chunk_records
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
                processing_status=ExtractionStatus.PROCESSING,
            )
            session.add(document)
            await session.flush()
            await session.refresh(document)
            document_id = document.id

            # ---------- 3. 切块 + 分批向量化（公共函数） ----------
            chunk_records = await build_chunk_records(
                tenant_id=tenant_id,
                document_id=document_id,
                cleaned_text=cleaned_text,
            )
            session.add_all(chunk_records)

            # ---------- 4. 完成：关联 DocumentFile + 翻转状态 ----------
            document.processing_status = ExtractionStatus.SUCCESS
            document.error_message = None
            session.add(document)

            doc_file.document_id = document_id
            doc_file.extraction_status = ExtractionStatus.SUCCESS
            doc_file.error_message = None
            session.add(doc_file)
            await session.commit()

        except Retry:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            await _handle_retryable_docfile(session, doc_file_id, job_try, exc)
        except httpx.HTTPStatusError as exc:
            # 5xx 服务端抖动可重试；4xx（key 错误/参数非法等）重试无意义
            if exc.response.status_code >= 500:
                await _handle_retryable_docfile(session, doc_file_id, job_try, exc)
            await _mark_docfile_failed(session, doc_file_id, exc)
        except Exception as exc:
            # ValueError/FileNotFoundError/PDF 解析错误等：数据问题，不重试
            await _mark_docfile_failed(session, doc_file_id, exc)

        await cache_delete_pattern(f"docfiles:list:tenant={tenant_id}:*")
        await cache_delete_pattern(f"docs:list:tenant={tenant_id}:*")


@func
async def rebuild_document_chunks(ctx: dict, document_id: int) -> None:
    """document create/update 接口的 ETL 任务。

    接口只负责：建 Document（status=PROCESSING）+ 入队 + 立即返回。
    本任务做剩下的事：切块 + 向量化 + 写 Chunks + 翻状态。
    """
    job_try: int = ctx.get("job_try", 1)

    async with new_session() as session:
        document = await session.get(Document, document_id)
        if document is None:
            logger.warning("document {} 不存在，任务安全退出", document_id)
            return

        tenant_id = document.tenant_id
        cleaned_text = document.content

        # ---------- 翻转 processing（含每一轮重试），并失效列表缓存 ----------
        document.processing_status = ExtractionStatus.PROCESSING
        document.error_message = None
        session.add(document)
        await session.commit()
        await cache_delete_pattern(f"docs:list:tenant={tenant_id}:*")

        try:
            # ---------- 幂等：重跑前清掉上一轮 Chunk ----------
            await session.exec(delete(Chunk).where(Chunk.document_id == document_id))

            # ---------- 切块 + 向量化（公共函数） ----------
            chunk_records = await build_chunk_records(
                tenant_id=tenant_id,
                document_id=document_id,
                cleaned_text=cleaned_text,
            )
            session.add_all(chunk_records)

            # ---------- 完成 ----------
            document.processing_status = ExtractionStatus.SUCCESS
            document.error_message = None
            session.add(document)
            await session.commit()

        except Retry:
            raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            await _handle_retryable_doc(session, document_id, job_try, exc)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                await _handle_retryable_doc(session, document_id, job_try, exc)
            await _mark_doc_failed(session, document_id, exc)
        except Exception as exc:
            await _mark_doc_failed(session, document_id, exc)

        await cache_delete_pattern(f"docs:list:tenant={tenant_id}:*")


# ---------------- 文件链路（DocumentFile）的错误处理 ----------------


async def _handle_retryable_docfile(
    session, doc_file_id: int, job_try: int, exc: Exception
) -> None:
    """可重试错误：未达上限则 rollback 后抛 Retry（arq 把 job 置 deferred，到点重跑）。"""
    max_tries = settings.arq_max_tries

    if job_try >= max_tries:
        logger.error(
            "doc_file {} 已尝试 {} 次仍失败，落 failed", doc_file_id, max_tries
        )
        await _mark_docfile_failed(session, doc_file_id, exc, retry_exhausted=True)
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


async def _mark_docfile_failed(
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


# ---------------- 文档直传链路（Document create/update）的错误处理 ----------------


async def _handle_retryable_doc(
    session, document_id: int, job_try: int, exc: Exception
) -> None:
    max_tries = settings.arq_max_tries

    if job_try >= max_tries:
        logger.error(
            "document {} 已尝试 {} 次仍失败，落 failed", document_id, max_tries
        )
        await _mark_doc_failed(session, document_id, exc, retry_exhausted=True)
        return

    await session.rollback()
    delay = _RETRY_DELAYS[min(job_try - 1, len(_RETRY_DELAYS) - 1)]
    logger.warning(
        "document {} 第 {}/{} 次尝试失败，{}s 后重试: {}",
        document_id,
        job_try,
        max_tries,
        delay,
        exc,
    )
    raise Retry(defer=timedelta(seconds=delay)) from exc


async def _mark_doc_failed(
    session, document_id: int, exc: Exception, retry_exhausted: bool = False
) -> None:
    await session.rollback()
    document = await session.get(Document, document_id)
    if document is None:
        return

    prefix = "重试次数耗尽: " if retry_exhausted else ""
    document.processing_status = ExtractionStatus.FAILED
    document.error_message = f"{prefix}{type(exc).__name__}: {exc}"[:500]
    session.add(document)
    await session.commit()
    logger.exception("document {} 处理失败", document_id)
