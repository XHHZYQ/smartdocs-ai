import re
from io import BytesIO

from pypdf import PdfReader

from app.models.document_file import SourceType


def extract_text(source_type: SourceType, raw_bytes: bytes) -> str:
    """同步阻塞函数：按来源类型分发到具体的提取实现。
    调用方必须用 run_in_threadpool 包裹，不能在 async 函数里直接调用。
    """
    if source_type == SourceType.PDF:
        return _extract_pdf_text(raw_bytes)
    if source_type == SourceType.MARKDOWN:
        return _extract_markdown_text(raw_bytes)
    raise ValueError(f"Unsupported source_type: {source_type}")


def _extract_pdf_text(raw_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(raw_bytes))
    # 单页提取失败（加密/扫描件等）时 extract_text() 可能返回 None，兜底成空字符串
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text)


def _extract_markdown_text(raw_bytes: bytes) -> str:
    try:
        return raw_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("File is not valid UTF-8 text") from e


def clean_text(text: str) -> str:
    """最小清洗规则：统一换行符、去除行尾空白、合并连续空行"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)  # 3 个以上连续空行压缩成 1 个空行
    return text.strip()