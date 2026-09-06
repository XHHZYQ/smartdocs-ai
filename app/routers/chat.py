import asyncio

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.response import EnvelopeRoute

router = APIRouter(prefix="/chat", tags=["chat"], route_class=EnvelopeRoute)


async def _fake_stream():
    """先用假数据验证 EnvelopeRoute + StreamingResponse 是否兼容，不涉及真实 LLM 调用"""
    for i in range(5):
        yield f"data: chunk-{i}\n\n"
        await asyncio.sleep(1)  # 故意每秒吐一次，方便你肉眼观察是不是"真流式"


@router.get("/ping-stream")
async def ping_stream() -> StreamingResponse:
    return StreamingResponse(_fake_stream(), media_type="text/event-stream")