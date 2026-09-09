from datetime import datetime, timezone

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.db import get_session, new_session
from app.core.deps import get_current_user
from app.core.response import EnvelopeRoute
from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.schemas.message import MessageRead
from app.services.llm import stream_chat
from app.services.prompt import build_messages
from app.services.retrieval import retrieve_chunks

router = APIRouter(prefix="/chat", tags=["chat"], route_class=EnvelopeRoute)


async def _get_or_create_conversation(
    session: AsyncSession, owner_id: int, conversation_id: int | None
) -> Conversation:
    if conversation_id is not None:
        conv = await session.get(Conversation, conversation_id)
        if conv is None or conv.owner_id != owner_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conv

    conv = Conversation(owner_id=owner_id)
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    return conv


async def _load_history(session: AsyncSession, conversation_id: int) -> list[dict[str, str]]:
    """取出该会话目前为止的全部历史消息，按时间正序。
    暂不做滑动窗口截断——历史多长就带多长，先跑通流程，token 超限了再优化。
    """
    result = await session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return [{"role": m.role.value, "content": m.content} for m in result.all()]


async def _sse_event_stream(
    query: str,
    top_k: int,
    owner_id: int,
    conversation_id: int,
    history: list[dict[str, str]],
):
    """检索 + 历史拼装 + LLM 流式调用，流结束后把完整回答落库。
    注意：这里不能用 FastAPI 依赖注入的 session——那个 session 会在 chat() 函数
    return 之后就被关闭，而这个生成器是在 return 之后才真正执行的，
    所以必须自己开一个独立生命周期的 session。
    """
    async with new_session() as session:
        rows = await retrieve_chunks(session, owner_id, query, top_k)
        chunks = [chunk.content for chunk, _title, _dist in rows]

        # messages = build_messages(query, chunks, history)
        messages = build_messages(query, chunks)  # todo: 后续再优化，这里先不考虑历史消息

        full_reply = ""
        async for piece in stream_chat(messages):
            full_reply += piece
            payload = json.dumps({"content": piece}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

        session.add(
            Message(conversation_id=conversation_id, role=MessageRole.ASSISTANT, content=full_reply)
        )
        conversation = await session.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.updated_at = datetime.now(timezone.utc)
            session.add(conversation)
        await session.commit()

    yield "data: [DONE]\n\n"


@router.post("/complete")
async def chat(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    user_id = current_user.id
    conversation = await _get_or_create_conversation(
        session, user_id, payload.conversation_id
    )
    conversation_id = conversation.id  # commit 前先取出普通 int，避免过期对象访问报错

    history = await _load_history(session, conversation_id)

    # 用户消息先落库：即便生成阶段报错，至少这条提问留了记录
    session.add(
        Message(conversation_id=conversation_id, role=MessageRole.USER, content=payload.query)
    )
    await session.commit()

    return StreamingResponse(
        _sse_event_stream(
            payload.query, payload.top_k, user_id, conversation_id, history
        ),
        media_type="text/event-stream",
        headers={"X-Conversation-Id": str(conversation_id)},
    )


# 方便调试/前端加载历史用：查看某个会话目前存了哪些消息
@router.get("/history/{conversation_id}", response_model=list[MessageRead])
async def get_history(
    conversation_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[MessageRead]:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await session.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.all())