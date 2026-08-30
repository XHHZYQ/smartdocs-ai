import httpx2

from app.core.config import settings


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """批量调用 SiliconFlow API 生成向量，texts 顺序与返回的向量顺序一一对应"""
    if not texts:
        return []

    async with httpx2.AsyncClient(
        base_url=settings.embedding_base_url, timeout=30
    ) as client:
        response = await client.post(
            "/embeddings",
            headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
            json={"model": settings.embedding_model, "input": texts},
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]