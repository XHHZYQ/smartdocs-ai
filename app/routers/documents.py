from datetime import UTC, datetime

from app.core.db import get_session
from app.schemas.document import DocumentCreate, DocumentRead, DocumentUpdate
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.document import Document
from app.core.response import EnvelopeRoute
from app.core.deps import get_current_user
from app.models.user import User
from app.core.deps import get_current_user, get_tenant_context, require_role, TenantContext
from app.models.tenant import TenantRole

router = APIRouter(prefix="/documents", tags=["documents"], route_class=EnvelopeRoute)


# 创建文档
@router.post("/create", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    tenant_ctx: TenantContext = Depends(require_role(TenantRole.MEMBER)),
) -> Document:
    doc = Document(
        title=payload.title,
        content=payload.content,
        owner_id=current_user.id,
        tenant_id=tenant_ctx.tenant_id
    )
    session.add(doc)
    await session.commit()
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
    offset = (page - 1) * page_size
    result = await session.exec(
        select(Document)
        .where(Document.tenant_id == tenant_ctx.tenant_id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    return result.all()


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
    for field, value in updates.items():
        setattr(doc, field, value)
    doc.updated_at = datetime.now(UTC)

    session.add(doc)
    await session.commit()
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

    # 3. 删除文档本身
    # 以后软删除：改成 doc.deleted_at = ...; session.add(doc)
    # 以后审计：在这里插 AuditLog(before=snapshot, action="document.delete")
    await session.delete(doc)
    await session.commit()
