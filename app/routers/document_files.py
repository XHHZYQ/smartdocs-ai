from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.document_file import DocumentFile, ExtractionStatus, SourceType
from app.schemas.document_file import DocumentFileRead
from app.core.response import EnvelopeRoute

from starlette.concurrency import run_in_threadpool

from app.models.document import Document
from app.services.extraction import clean_text, extract_text

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
    session: AsyncSession = Depends(get_session),
) -> DocumentFile:
    source_type = _ALLOWED_CONTENT_TYPES.get(file.content_type)
    if source_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {file.content_type}",
        )

    raw_bytes = await file.read()

    doc_file = DocumentFile(
        original_filename=file.filename or "unknown",
        content_type=file.content_type,
        file_size_bytes=len(raw_bytes),
        source_type=source_type,
        extraction_status=ExtractionStatus.PENDING,
    )
    session.add(doc_file)
    await session.commit()
    await session.refresh(doc_file)

    try:
        raw_text = await run_in_threadpool(extract_text, source_type, raw_bytes)
        cleaned_text = clean_text(raw_text)

        if not cleaned_text:
            raise ValueError("Extracted text is empty")

        document = Document(title=doc_file.original_filename, content=cleaned_text)
        session.add(document)
        await session.commit()
        await session.refresh(document)

        doc_file.document_id = document.id
        doc_file.extraction_status = ExtractionStatus.SUCCESS
    except Exception as e:
        doc_file.extraction_status = ExtractionStatus.FAILED
        doc_file.error_message = str(e)[:500]

    session.add(doc_file)
    await session.commit()
    await session.refresh(doc_file)

    return doc_file
