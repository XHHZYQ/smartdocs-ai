from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from sqlalchemy import func
from sqlmodel import select
import filetype 

from app.core.db import get_session
from app.models.user import User
from app.models.document import Document
from app.models.document_file import DocumentFile, ExtractionStatus, SourceType
from app.schemas.document_file import DocumentFileRead, DocumentFilePage
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
@router.get("", response_model=DocumentFilePage)
async def list_document_files(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: ExtractionStatus | None = Query(None),
    q: str | None = Query(None, min_length=1, max_length=255),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentFilePage:
    conditions = [DocumentFile.owner_id == current_user.id]

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

    return DocumentFilePage(items=items, total=total)   


@router.post("", response_model=DocumentFileRead, status_code=status.HTTP_201_CREATED)
async def upload_document_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DocumentFile:
    raw_bytes = await file.read()
    source_type = _resolve_source_type(file.filename or "", raw_bytes)
    if source_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported or unrecognized file type",
        )

    owner_id = current_user.id  # 在任何 commit 之前，先把 id 取出来存成普通 int，解决 greenlet_spawn has not been called 报错

    doc_file = DocumentFile(
        original_filename=file.filename or "unknown",
        content_type=file.content_type,
        file_size_bytes=len(raw_bytes),
        source_type=source_type,
        extraction_status=ExtractionStatus.PENDING,
        owner_id=owner_id
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
        await session.flush()
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
