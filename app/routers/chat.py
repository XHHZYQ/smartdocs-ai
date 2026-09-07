import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.core.response import EnvelopeRoute
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.llm import stream_chat
from app.services.prompt import build_messages
from app.services.retrieval import retrieve_chunks

router = APIRouter(prefix="/chat", tags=["chat"], route_class=EnvelopeRoute)


async def _sse_event_stream(query: str, top_k: int, session: AsyncSession, owner_id: int):
    """把检索 + LLM 流式调用串起来，逐帧产出标准 SSE 格式文本。"""
    rows = await retrieve_chunks(session, owner_id, query, top_k)
    chunks = [chunk.content for chunk, _title, _dist in rows]
    print("retrieve_chunks chunks:", chunks)

    messages = build_messages(query, chunks)
    print("build_messages messages:", messages)

    async for piece in stream_chat(messages):
        payload = json.dumps({"content": piece}, ensure_ascii=False)
        yield f"data: {payload}\n\n"

    yield "data: [DONE]\n\n"


@router.post("/complete")
async def chat(
    payload: ChatRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    return StreamingResponse(
        _sse_event_stream(payload.query, payload.top_k, session, current_user.id),
        media_type="text/event-stream",
    )