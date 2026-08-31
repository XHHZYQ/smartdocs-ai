"""临时验证脚本：确认 SiliconFlow embedding API 链路通、维度对"""
import asyncio

import httpx2

from app.core.config import settings


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    async with httpx2.AsyncClient(
        base_url=settings.embedding_base_url, timeout=30
    ) as client:
        response = await client.post(
            "/embeddings",
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
            json={"model": settings.embedding_model, "input": texts},
        )
        response.raise_for_status()  # 4xx/5xx 直接抛异常，方便先看到真实错误信息
        data = response.json()
        return [item["embedding"] for item in data["data"]]


async def main():
    texts = ["这是第一段测试文本", "这是第二段完全不同内容的文本"]
    embeddings = await get_embeddings(texts)

    print(f"返回 {len(embeddings)} 条向量")
    for i, vec in enumerate(embeddings):
        print(f"第 {i} 条 -> 维度: {len(vec)}, 前 5 个值: {vec[:5]}")

    assert len(embeddings[0]) == settings.embedding_dimensions, (
        f"维度不匹配！config 配置的是 {settings.embedding_dimensions}，"
        f"API 实际返回 {len(embeddings[0])}"
    )
    print("维度校验通过 ✅")


if __name__ == "__main__":
    asyncio.run(main())