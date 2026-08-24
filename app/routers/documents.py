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

router = APIRouter(prefix="/documents", tags=["documents"], route_class=EnvelopeRoute)


# create_document
@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
async def create_document(
    payload: DocumentCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Document:
    doc = Document(title=payload.title, content=payload.content, owner_id=current_user.id)
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    return doc


# list_documents
@router.get("", response_model=list[DocumentRead])
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[Document]:
    result = await session.exec(
        select(Document)
        .where(Document.owner_id == current_user.id)
        .order_by(Document.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.all()


@router.get("/{document_id}", response_model=DocumentRead)
async def get_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None or doc.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.patch("/{document_id}", response_model=DocumentRead)
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


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    session: AsyncSession = Depends(get_session),
) -> None:
    doc = await session.get(Document, document_id)
    if doc is None or doc.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Document not found")
    await session.delete(doc)
    await session.commit()
