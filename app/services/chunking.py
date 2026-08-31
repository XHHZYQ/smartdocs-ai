import re

_CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)

def _split_into_paragraphs(text: str) -> list[str]:
    """段落切分：把代码块（```...```）当作不可再拆的整体，
    避免代码块内部的空行被误判为段落分隔符，导致代码和说明文字被强行拆散。
    """
    paragraphs: list[str] = []
    last_end = 0

    for match in _CODE_BLOCK_PATTERN.finditer(text):
        before = text[last_end : match.start()]
        paragraphs.extend(p.strip() for p in before.split("\n\n") if p.strip())

        code_block = match.group().strip()
        if code_block:
            paragraphs.append(code_block)

        last_end = match.end()

    tail = text[last_end:]
    paragraphs.extend(p.strip() for p in tail.split("\n\n") if p.strip())

    return paragraphs


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """段落感知切块：优先按空行分段，贪心合并到接近 chunk_size；
    单个段落超长时才退化为字符滑动窗口。纯函数，不涉及 DB/IO。
    """
    if not text:
        return []

    paragraphs = _split_into_paragraphs(text)

    chunks: list[str] = []
    buffer = ""

    for para in paragraphs:
        if len(para) > chunk_size:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_split_long_paragraph(para, chunk_size, overlap))
            continue

        candidate = f"{buffer}\n\n{para}" if buffer else para
        if len(candidate) <= chunk_size:
            buffer = candidate
        else:
            chunks.append(buffer)
            buffer = para

    if buffer:
        chunks.append(buffer)

    return chunks


def _split_long_paragraph(paragraph: str, chunk_size: int, overlap: int) -> list[str]:
    """单段落超过 chunk_size 时的兜底：字符级滑动窗口"""
    chunks = []
    start = 0
    text_len = len(paragraph)
    while start < text_len:
        end = start + chunk_size
        chunks.append(paragraph[start:end])
        if end >= text_len:
            break
        start = end - overlap
    return chunks