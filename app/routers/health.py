"""健康检查端点。

职责区分（Kubernetes/ALB 探活的标准约定）：
- /health    liveness：进程活着就 200，不查依赖。
                失败时编排才重启容器，避免误判把好容器杀掉。
- /readiness readiness：探 DB + Redis，任一不可用返回 503。
                失败时编排只把流量摘掉（不重启），等依赖恢复。

不依赖 Depends：lifespan 初始化失败时 redis_client 为 None，
Depends 会抛 RuntimeError 被异常处理器兜成 500，对探活不友好；
直接用全局单例 + try/except 才能精确返回 503 + 检查项明细。
"""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core import redis as redis_module
from app.core.db import engine

# 健康检查不走统一 envelope（{code,data,msg}），探活工具看简洁字段更顺
router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """liveness：进程活着就 ok，不查依赖。"""
    return {"status": "ok"}


@router.get("/readiness", response_model=None)
async def readiness() -> JSONResponse | dict:
    """readiness：探 DB + Redis，任一不可用返回 503。"""
    checks: dict[str, str] = {}
    ok = True

    # DB check：用全局 engine 直接 connect，不走 session
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"fail: {type(e).__name__}"
        ok = False

    # Redis check：直接拿全局单例，None 时也归到 fail 分支
    try:
        if redis_module.redis_client is None:
            raise RuntimeError("redis not initialized")
        await redis_module.redis_client.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"fail: {type(e).__name__}"
        ok = False

    if not ok:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "fail", "checks": checks},
        )
    return {"status": "ok", "checks": checks}
