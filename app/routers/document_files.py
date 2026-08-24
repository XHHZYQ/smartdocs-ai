from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.document_file import DocumentFile, ExtractionStatus, SourceType
from app.schemas.document_file import DocumentFileRead

router = APIRouter(prefix="/document-files", tags=["document-files"])

# content-type -> source_type 的粗筛映射，后续可以换成更严格的文件头校验
_ALLOWED_CONTENT_TYPES: dict[str, SourceType] = {
    "application/pdf": SourceType.PDF,
    "text/markdown": SourceType.MARKDOWN,
    "text/plain": SourceType.MARKDOWN,  # 部分客户端把 .md 标成 text/plain
}


@router.post(
    "", response_model=DocumentFileRead, status_code=status.HTTP_201_CREATED
)
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

    # TODO(下一步): 调用 run_in_threadpool 做文本提取 + 清洗
    #   - 成功: 创建 Document，写回 doc_file.document_id，status = SUCCESS
    #   - 失败: doc_file.error_message = str(e)，status = FAILED
    #   这里先只落库 pending 状态，验证上传链路本身能跑通

    return doc_file