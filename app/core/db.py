from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=True)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with SQLModelAsyncSession(engine) as session:
        yield session


def new_session() -> SQLModelAsyncSession:
    """给需要脱离 FastAPI 请求生命周期、自行管理 session 的场景用(比如 SSE 生成器)。
    用法: async with new_session() as session: ...
    """
    return SQLModelAsyncSession(engine)
