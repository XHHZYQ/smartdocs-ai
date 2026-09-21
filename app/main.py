import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from loguru import logger
from fastapi.middleware.cors import CORSMiddleware

# from app.core.db import init_db
from app.routers import auth, documents, document_files, search, chat, tenant, debug
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.redis import init_redis, close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    # await init_db()  # 已使用 Alembic，保持注释

    # ===== 启动时连 Redis =====
    await init_redis()

    yield

    # ===== 关闭时断开 Redis =====
    await close_redis()


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

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms:.1f}ms)"
    )
    return response

app.include_router(debug.router)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(document_files.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(tenant.router)


@app.get("/")
def read_root():
    return {"status": "ok"}
