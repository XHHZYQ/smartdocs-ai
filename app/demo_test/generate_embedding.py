import asyncio
import random

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.models.chunk import Chunk


async def seed_fake_chunks(count: int = 5000):
    async with AsyncSession(engine) as session:
        base_vector = [random.random() for _ in range(1024)]
        records = [
            Chunk(
                document_id=1,  # 用你库里已存在的某个 document_id
                chunk_index=i,
                content=f"fake chunk {i}",
                char_count=10,
                embedding=[v + random.uniform(-0.01, 0.01) for v in base_vector],
            )
            for i in range(count)
        ]
        session.add_all(records)
        await session.commit()
        print(f"插入了 {count} 条测试数据")


if __name__ == "__main__":
    asyncio.run(seed_fake_chunks())