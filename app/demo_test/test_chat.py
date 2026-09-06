# 临时测试脚本，跑通后可删除
import asyncio
from app.services.llm import stream_chat


async def main():
    messages = [{"role": "user", "content": "用一句话介绍一下你自己"}]
    async for piece in stream_chat(messages):
        print(piece, end="", flush=True)  # end="" 让输出看起来是连续吐字，而不是分行
    print()


asyncio.run(main())