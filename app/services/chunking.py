def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """段落感知切块：优先按空行分段，贪心合并到接近 chunk_size；
    单个段落超长时才退化为字符滑动窗口。纯函数，不涉及 DB/IO。
    """
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

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