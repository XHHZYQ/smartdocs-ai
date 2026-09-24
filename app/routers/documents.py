from datetime import UTC, datetime
from loguru import logger

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import delete, select, update

from app.core.cache import build_cache_key, cache_delete_pattern, cache_get, cache_set
from app.core.db import get_session
from app.core.deps import (
    TenantContext,
    get_current_user,
    get_tenant_context,
    require_role,
)
from app.core.limiter import limiter
from app.core.queue import enqueue_rebuild_chunks
from app.core.response import EnvelopeRoute
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.document_file import DocumentFile, ExtractionStatus
from app.models.tenant import TenantRole
from app.models.user import User
from app.schemas.document import DocumentCreate, DocumentRead, DocumentUpdate
from app.services.extraction import clean_text

router = APIRouter(prefix="/documents", tags=["documents"], route_class=EnvelopeRoute)


# 创建文档
@router.post(
    "/create", response_model=DocumentRead, status_code=status.HTTP_201_CREATED
)
@limiter.limit("30/minute")
async def create_document(
    request: Request,
    payload: DocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(require_role(TenantRole.MEMBER)),
) -> Document:
    cleaned = clean_text(payload.content)
    if not cleaned:
        raise HTTPException(
            status_code=400, detail="Document content is empty after cleaning"
        )

    doc = Document(
        title=payload.title,
        content=cleaned,
        owner_id=current_user.id,
        tenant_id=tenant_ctx.tenant_id,
        # 入队后由 arq worker 翻 success/failed；接口立即返回 processing
        processing_status=ExtractionStatus.PROCESSING,
    )
    session.add(doc)
    await session.flush()  # 拿到 doc.id，还没 commit
    await session.refresh(doc)
    document_id = doc.id

    await session.commit()
    await cache_delete_pattern(f"docs:list:tenant={tenant_ctx.tenant_id}:*")
    await session.refresh(doc)

    # 入队切块+向量化。队列不可用不应让"创建"失败：记录已落库，状态 processing，
    # 记日志，后续可手动触发重试（或前端轮询时发现仍 processing 由 retry 接口兜底）
    try:
        await enqueue_rebuild_chunks(document_id)
    except Exception:
        logger.exception("document {} 入队失败，可稍后调用 retry 接口", document_id)

    return doc


# 获取用户文档列表
@router.get("/list", response_model=list[DocumentRead])
@limiter.limit("120/minute")
async def list_documents(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> list[Document]:
    cache_key = build_cache_key(
        "docs:list",
        tenant=tenant_ctx.tenant_id,
        page=page,
        size=page_size,
    )

    # 1. 先查缓存
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached  # 已经是 list[dict]，Pydantic 会再校验

    # 2. 未命中 → 查 DB
    offset = (page - 1) * page_size
    result = await session.exec(
        select(Document)
        .where(Document.tenant_id == tenant_ctx.tenant_id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    docs = result.all()

    # 3. 写入缓存（TTL 60s）
    # Document 是 SQLModel，转成可序列化的 dict
    payload = [doc.model_dump(mode="json") for doc in docs]
    await cache_set(cache_key, payload, ttl=60)

    return docs


# 根据 id 获取文档
@router.get("/detail/{document_id}", response_model=DocumentRead)
@limiter.limit("60/minute")
async def get_document(
    request: Request,
    document_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None or doc.tenant_id != tenant_ctx.tenant_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


# 更新文档
@router.patch("/update/{document_id}", response_model=DocumentRead)
@limiter.limit("30/minute")
async def update_document(
    request: Request,
    document_id: int,
    payload: DocumentUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None or doc.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")

    updates = payload.model_dump(exclude_unset=True)
    content_changed = "content" in updates

    if content_changed:
        cleaned = clean_text(updates["content"] or "")
        if not cleaned:
            raise HTTPException(
                status_code=400, detail="Document content is empty after cleaning"
            )
        updates["content"] = cleaned

    for field, value in updates.items():
        setattr(doc, field, value)
    doc.updated_at = datetime.now(UTC)

    # 只有正文变了才重建 Chunk；只改 title 不动向量库
    if content_changed:
        # 翻 processing，由 arq worker 完成切块+向量化后翻 success/failed
        doc.processing_status = ExtractionStatus.PROCESSING
        doc.error_message = None

    session.add(doc)
    await session.commit()
    # 更新文档后需要删除缓存，保持缓存一致性
    await cache_delete_pattern(f"docs:list:tenant={doc.tenant_id}:*")
    await session.refresh(doc)

    # content 变了才入队；title-only 更新不入队
    if content_changed:
        try:
            await enqueue_rebuild_chunks(document_id)
        except Exception:
            logger.exception("document {} 入队失败，可稍后调用 retry 接口", document_id)

    return doc


# 删除文档
@router.delete("/delete/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("30/minute")
async def delete_document(
    request: Request,
    document_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> None:
    doc = await session.get(Document, document_id)
    if doc is None or doc.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    # 1. 显式删除关联 Chunk
    await session.exec(delete(Chunk).where(Chunk.document_id == document_id))

    # 2. DocumentFile 只断开关联
    await session.exec(
        update(DocumentFile)
        .where(DocumentFile.document_id == document_id)
        .values(document_id=None)
    )

    tenant_id = doc.tenant_id

    # 3. 删除文档本身
    # 以后软删除：改成 doc.deleted_at = ...; session.add(doc)
    # 以后审计：在这里插 AuditLog(before=snapshot, action="document.delete")
    await session.delete(doc)
    await session.commit()
    await cache_delete_pattern(f"docs:list:tenant={tenant_id}:*")
