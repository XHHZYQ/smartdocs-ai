from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.db import get_session
from app.models.user import User
from app.models.document import Document
from app.models.document_file import DocumentFile, ExtractionStatus, SourceType
from app.schemas.document_file import DocumentFileRead
from app.core.response import EnvelopeRoute
from app.core.deps import get_current_user
from app.services.extraction import clean_text, extract_text
from app.models.chunk import Chunk
from app.services.chunking import chunk_text
from app.services.embedding import get_embeddings


router = APIRouter(
    prefix="/document-files", tags=["document-files"], route_class=EnvelopeRoute
)

# content-type -> source_type 的粗筛映射，后续可以换成更严格的文件头校验
_ALLOWED_CONTENT_TYPES: dict[str, SourceType] = {
    "application/pdf": SourceType.PDF,
    "text/markdown": SourceType.MARKDOWN,
    "text/plain": SourceType.MARKDOWN,  # 部分客户端把 .md 标成 text/plain
}


@router.post("", response_model=DocumentFileRead, status_code=status.HTTP_201_CREATED)
async def upload_document_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentFile:
    source_type = _ALLOWED_CONTENT_TYPES.get(file.content_type)
    if source_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {file.content_type}",
        )

    raw_bytes = await file.read()
    owner_id = current_user.id  # 在任何 commit 之前，先把 id 取出来存成普通 int，解决 greenlet_spawn has not been called 报错

    doc_file = DocumentFile(
        original_filename=file.filename or "unknown",
        content_type=file.content_type,
        file_size_bytes=len(raw_bytes),
        source_type=source_type,
        extraction_status=ExtractionStatus.PENDING,
    )
    # session.add(doc_file)
    # await session.commit()
    # await session.refresh(doc_file)

    try:
        raw_text = await run_in_threadpool(extract_text, source_type, raw_bytes)
        cleaned_text = clean_text(raw_text)

        if not cleaned_text:
            raise ValueError("Extracted text is empty")

        document = Document(title=doc_file.original_filename, content=cleaned_text, owner_id=owner_id)
        session.add(document)
        await session.commit()
        await session.refresh(document)

        document_id = document.id

        chunks = chunk_text(cleaned_text)
        embeddings = await get_embeddings(chunks)  # 新增：批量生成向量，和 chunks 顺序一一对应

        chunk_records = [
            Chunk(
                document_id=document_id,
                chunk_index=idx,
                content=chunk,
                char_count=len(chunk),
                embedding=embedding
            )
            for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings))
        ]
        session.add_all(chunk_records)
        await session.commit()
        
        doc_file.document_id = document_id
        doc_file.extraction_status = ExtractionStatus.SUCCESS
    except Exception as e:
        await session.rollback()  # 回滚事务，确保数据库的一致性
        doc_file.extraction_status = ExtractionStatus.FAILED
        doc_file.error_message = str(e)[:500]

    session.add(doc_file)
    await session.commit()
    await session.refresh(doc_file)

    return doc_file
