from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import init_db
from app.routers import auth, documents, document_files
from app.core.exceptions import register_exception_handlers


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)
register_exception_handlers(app)
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(document_files.router)


@app.get("/")
def read_root():
    return {"status": "ok"}
