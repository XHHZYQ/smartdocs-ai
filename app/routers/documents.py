from datetime import UTC, datetime

from app.core.db import get_session
from app.schemas.document import DocumentCreate, DocumentRead, DocumentUpdate
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, delete, update

from app.models.document import Document
from app.core.response import EnvelopeRoute
from app.core.deps import get_current_user
from app.models.user import User
from app.models.chunk import Chunk
from app.models.document_file import DocumentFile
from app.core.deps import get_current_user, get_tenant_context, require_role, TenantContext
from app.models.tenant import TenantRole
from app.services.extraction import clean_text
from app.services.chunking import chunk_text
from app.services.embedding import get_embeddings
from app.core.cache import build_cache_key, cache_get, cache_set, cache_delete_pattern
from app.core.redis import get_redis  # 如果后面要 Depends 也可以，这里直接用工具函数即可

router = APIRouter(prefix="/documents", tags=["documents"], route_class=EnvelopeRoute)

async def _rebuild_chunks(
    session: AsyncSession,
    *,
    document_id: int,
    tenant_id: int,
    cleaned_text: str,
) -> None:
    """删除旧 Chunk，按清洗后的文本重新切块 + 向量化并写入。"""
    await session.exec(delete(Chunk).where(Chunk.document_id == document_id))

    chunks = chunk_text(cleaned_text)
    if not chunks:
        return

    embeddings = await get_embeddings(chunks)
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


# 创建文档
@router.post("/create", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(require_role(TenantRole.MEMBER)),
) -> Document:
    cleaned = clean_text(payload.content)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Document content is empty after cleaning")

    doc = Document(
        title=payload.title,
        content=cleaned,
        owner_id=current_user.id,
        tenant_id=tenant_ctx.tenant_id,
    )
    session.add(doc)
    await session.flush()          # 拿到 doc.id，还没 commit
    await session.refresh(doc)

    await _rebuild_chunks(
        session,
        document_id=doc.id,
        tenant_id=tenant_ctx.tenant_id,
        cleaned_text=cleaned,
    )
    await session.commit()
    await cache_delete_pattern(f"docs:list:tenant={tenant_ctx.tenant_id}:*")
    await session.refresh(doc)
    return doc


# 获取用户文档列表
@router.get("/list", response_model=list[DocumentRead])
async def list_documents(
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
async def get_document(
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
async def update_document(
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
            raise HTTPException(status_code=400, detail="Document content is empty after cleaning")
        updates["content"] = cleaned

    for field, value in updates.items():
        setattr(doc, field, value)
    doc.updated_at = datetime.now(UTC)

    session.add(doc)

    # 只有正文变了才重建 Chunk；只改 title 不动向量库
    if content_changed:
        await _rebuild_chunks(
            session,
            document_id=doc.id,
            tenant_id=doc.tenant_id,
            cleaned_text=doc.content,
        )

    await session.commit()
    # 更新文档后需要删除缓存，保持缓存一致性
    await cache_delete_pattern(f"docs:list:tenant={doc.tenant_id}:*")
    await session.refresh(doc)
    return doc

# 删除文档
@router.delete("/delete/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
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
