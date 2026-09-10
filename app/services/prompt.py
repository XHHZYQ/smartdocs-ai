SYSTEM_PROMPT = (
    "你是一个基于给定资料回答问题的助手，只根据【参考资料】作答，"
    "如果资料里没有答案就明确说不知道，不要编造。"
)

_MAX_CONTEXT_CHARS = 3000  # 参考资料总字符数上限，超出则丢弃后面（相关度更低）的 chunk


def build_messages(
    query: str,
    chunks: list[str],
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """把检索到的 chunk 列表 + 历史会话 + 用户问题，拼装成 Chat Completions 接口需要的 messages 格式。
    按 _MAX_CONTEXT_CHARS 做截断，超过阈值的 chunk 直接丢弃（chunks 已按相关度排好序）。
    history 为该会话此前的消息列表（按时间正序，每项形如 {"role": "user"/"assistant", "content": ...}），
    会原样插入到 system 消息之后、当前用户问题之前。
    """
    context_parts: list[str] = []
    total_chars = 0

    for idx, content in enumerate(chunks, start=1):
        if total_chars + len(content) > _MAX_CONTEXT_CHARS:
            break  # 后面相关度更低，直接丢弃，不做部分截断
        context_parts.append(f"[{idx}] {content}")
        total_chars += len(content)

    context = "\n\n".join(context_parts)

    user_content = f"【参考资料】\n{context}\n\n【用户问题】\n{query}"

    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_content})
    return messages