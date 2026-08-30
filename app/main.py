from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import init_db
from app.routers import auth, documents, document_files, search
from app.core.exceptions import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    # await init_db() # 已使用 Alembic 进行数据库迁移, 不需要再初始化数据库
    yield


app = FastAPI(lifespan=lifespan)
register_exception_handlers(app)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(document_files.router)
app.include_router(search.router)


@app.get("/")
def read_root():
    return {"status": "ok"}
