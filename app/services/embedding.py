import httpx
from loguru import logger

from app.core.config import settings


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """批量调用 SiliconFlow API 生成向量，texts 顺序与返回顺序一一对应。

    大文件切块可能成百上千，单次请求有数量/token 上限，按 embedding_batch_size 分批；
    任一批失败则直接抛出（由 arq 任务判断是否重试），成功时返回完整结果且顺序不变。
    """
    if not texts:
        return []

    all_embeddings: list[list[float]] = []
    batch_size = settings.embedding_batch_size
    total_batches = (len(texts) + batch_size - 1) // batch_size

    async with httpx.AsyncClient(
        base_url=settings.embedding_base_url, timeout=30
    ) as client:
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            response = await client.post(
                "/embeddings",
                headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
                json={"model": settings.embedding_model, "input": batch},
            )
            response.raise_for_status()
            data = response.json()
            all_embeddings.extend(item["embedding"] for item in data["data"])
            logger.info(
                "embedding batch {}/{} done ({} chunks)",
                start // batch_size + 1,
                total_batches,
                len(batch),
            )

    return all_embeddings
