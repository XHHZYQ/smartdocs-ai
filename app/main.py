from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import init_db
from app.routers import documents


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(documents.router)


@app.get("/")
def read_root():
    return {"status": "ok"}
