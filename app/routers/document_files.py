import filetype
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from loguru import logger
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from starlette.concurrency import run_in_threadpool

from app.core.cache import (
    build_cache_key,
    cache_delete_pattern,
    cache_get,
    cache_set,
)  # 如果后面要 Depends 也可以，这里直接用工具函数即可
from app.core.db import get_session
from app.core.deps import (
    TenantContext,
    get_current_user,
    get_tenant_context,
    require_role,
)
from app.core.limiter import limiter
from app.core.queue import enqueue_document_job
from app.core.response import EnvelopeRoute
from app.models.document_file import DocumentFile, ExtractionStatus, SourceType
from app.models.tenant import TenantRole
from app.models.user import User
from app.schemas.document_file import DocumentFilePage, DocumentFileRead
from app.services.storage import file_exists, save_file

router = APIRouter(
    prefix="/document-files", tags=["document-files"], route_class=EnvelopeRoute
)

# content-type -> source_type 的粗筛映射，后续可以换成更严格的文件头校验
_ALLOWED_CONTENT_TYPES: dict[str, SourceType] = {
    "application/pdf": SourceType.PDF,
    "text/markdown": SourceType.MARKDOWN,
    "text/plain": SourceType.MARKDOWN,  # 部分客户端把 .md 标成 text/plain
}


def _resolve_source_type(filename: str, raw_bytes: bytes) -> SourceType | None:
    """内容嗅探优先，文件名后缀兜底。不再信任 content_type 请求头。"""
    kind = filetype.guess(raw_bytes)
    if kind is not None:
        # 命中已知二进制格式的文件头特征，这是最可靠的判断依据
        if kind.mime == "application/pdf":
            return SourceType.PDF
        return None  # 识别出是别的二进制格式（比如图片、zip），但不在支持范围，直接拒绝

    # 没有命中任何已知二进制签名 —— 纯文本类文件（含 md/txt）天然都会走到这里
    # 这一步没有"确定性"可言，只能靠文件名兜底
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {"md", "markdown", "txt"}:
        return SourceType.MARKDOWN

    return None


# 必须放在其他带路径参数的路由(比如以后有 /document-files/{id})之前,否则 FastAPI 会先匹配到路径参数路由
# 获取用户文档文件列表
@router.get("/list", response_model=DocumentFilePage)
@limiter.limit("120/minute")
async def list_document_files(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    status: ExtractionStatus | None = Query(None),
    q: str | None = Query(None, min_length=1, max_length=255),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> DocumentFilePage:
    cache_key = build_cache_key(
        "docfiles:list",
        tenant=tenant_ctx.tenant_id,
        page=page,
        size=page_size,
        status=status.value if status else None,
        q=q,
    )

    cached = await cache_get(cache_key)
    if cached is not None:
        return DocumentFilePage(**cached)

    # ---------- 原有 DB 查询逻辑保持不变 ----------
    skip = (page - 1) * page_size  # 在函数内部换算，对外语义更直观
    limit = page_size
    conditions = [DocumentFile.tenant_id == tenant_ctx.tenant_id]

    if status is not None:
        conditions.append(DocumentFile.extraction_status == status)

    if q:
        conditions.append(DocumentFile.original_filename.ilike(f"%{q}%"))

    # 总数:同一组 conditions 单独跑一次 count 查询
    count_result = await session.exec(
        select(func.count()).select_from(DocumentFile).where(*conditions)
    )
    total = count_result.one()

    # 数据:按上传时间倒序，分页
    result = await session.exec(
        select(DocumentFile)
        .where(*conditions)
        .order_by(DocumentFile.uploaded_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = result.all()

    page_data = DocumentFilePage(
        items=items, total=total, page=page, page_size=page_size
    )

    # 写入缓存
    await cache_set(
        cache_key,
        page_data.model_dump(mode="json"),
        ttl=60,
    )
    return page_data


# 上传文档文件（异步处理）
# API 只负责：校验 → 落库 pending → 原始文件落盘 → 入队，立即返回
# 重 ETL（提取/切块/向量化）由 arq worker 跑 app.tasks.document_jobs.process_document_file
@router.post(
    "/upload", response_model=DocumentFileRead, status_code=status.HTTP_201_CREATED
)
@limiter.limit("20/minute")
async def upload_document_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(require_role(TenantRole.MEMBER)),
    session: AsyncSession = Depends(get_session),
) -> DocumentFile:
    raw_bytes = await file.read()
    source_type = _resolve_source_type(file.filename or "", raw_bytes)
    if source_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported or unrecognized file type",
        )

    # 1. 先落库 pending，flush 拿 id（磁盘文件用 id 命名）
    doc_file = DocumentFile(
        original_filename=file.filename or "unknown",
        content_type=file.content_type,
        file_size_bytes=len(raw_bytes),
        source_type=source_type,
        extraction_status=ExtractionStatus.PENDING,
        owner_id=current_user.id,
        tenant_id=tenant_ctx.tenant_id,
    )
    session.add(doc_file)
    await session.flush()
    doc_file_id = doc_file.id

    # 2. 原始文件落盘（阻塞 IO 丢线程池），成功后才 commit
    await run_in_threadpool(save_file, doc_file_id, raw_bytes)
    await session.commit()
    await session.refresh(doc_file)

    # 3. 入队。队列不可用不应让"上传"失败：文件已存、状态 pending，记日志，retry 接口兜底
    try:
        await enqueue_document_job(doc_file_id)
    except Exception:
        logger.exception("doc_file {} 入队失败，可稍后调用 retry 接口", doc_file_id)

    # 4. 列表新增了记录，失效列表缓存
    await cache_delete_pattern(
        f"docfiles:list:tenant={tenant_ctx.tenant_id}:*"
    )
    return doc_file


# 手动重试处理失败的文件：校验状态/磁盘文件 → 回 pending → 重新入队
@router.post("/retry/{doc_file_id}", response_model=DocumentFileRead)
@limiter.limit("20/minute")
async def retry_document_file(
    request: Request,
    doc_file_id: int,
    tenant_ctx: TenantContext = Depends(require_role(TenantRole.MEMBER)),
    session: AsyncSession = Depends(get_session),
) -> DocumentFile:
    doc_file = await session.get(DocumentFile, doc_file_id)
    if doc_file is None or doc_file.tenant_id != tenant_ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document file not found"
        )

    if doc_file.extraction_status != ExtractionStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed files can be retried",
        )

    # 原始文件已不在磁盘则无法重跑
    if not await run_in_threadpool(file_exists, doc_file_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Original file no longer exists on disk",
        )

    doc_file.extraction_status = ExtractionStatus.PENDING
    doc_file.error_message = None
    session.add(doc_file)
    await session.commit()

    # 终态后固定 job_id 可重新入队；入队失败抛出让统一异常处理器兜底（本次是显式重试操作）
    await enqueue_document_job(doc_file_id)
    await cache_delete_pattern(
        f"docfiles:list:tenant={tenant_ctx.tenant_id}:*"
    )
    await session.refresh(doc_file)
    return doc_file
