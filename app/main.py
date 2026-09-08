from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# from app.core.db import init_db
from app.routers import auth, documents, document_files, search, chat
from app.core.exceptions import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    # await init_db() # 已使用 Alembic 进行数据库迁移, 不需要再初始化数据库
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Conversation-Id"],  # 让前端 fetch 能读到这个响应头
)
register_exception_handlers(app)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(document_files.router)
app.include_router(search.router)
app.include_router(chat.router)


@app.get("/")
def read_root():
    return {"status": "ok"}
