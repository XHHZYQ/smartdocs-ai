"""测试基础设施: DB 隔离 / Redis mock / arq no-op / 认证 fixture / 异步测试客户端。

设计思路（对照前端测试经验）:
- httpx.AsyncClient + ASGITransport  ≈ supertest，但原生 async
- fakeredis 替换真实 Redis              ≈ mock 整个 Redis 客户端
- monkeypatch 替换 arq 入队函数         ≈ mock MQ producer
- 每个测试后 truncate 所有表            ≈ beforeEach 清空数据库
- dependency_overrides 覆盖 get_session ≈ Fastify 里 override decorate 的 db
"""
import asyncio

import httpx
import pytest
import pytest_asyncio
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401 — 确保所有表注册到 metadata
import app.core.db as db_module
from app.core.config import settings
from app.core.db import new_session
from app.core.security import create_access_token, hash_password
from app.models.tenant import Tenant, TenantMembership, TenantRole
from app.models.user import User

# ===== 覆盖 engine: NullPool 不复用连接，每个 session 独占一个连接 =====
# asyncpg 的连接池在 Windows + 多事件循环场景下有竞态，
# NullPool 让 new_session() 每次创建新连接，session.close() 后彻底释放。
db_module.engine = create_async_engine(
    settings.database_url, poolclass=NullPool, echo=False
)


# ===== Session 级: 建表 / 销毁 =====
# 用同步 fixture + asyncio.run() 绕开 pytest-asyncio 的 session/function 事件循环冲突。
# pytest-asyncio 的 session 级 async fixture 在 Windows + Python 3.14 下会死锁，
# 改为同步 fixture 在独立事件循环里运行 async 代码即可。

@pytest.fixture(scope="session")
def _create_tables():
    """会话开始时建表，结束时删表。只跑一次。

    用独立 engine，不和 app.core.db.engine 共享连接池——
    asyncio.run() 创建的连接池绑定到它的事件循环，
    和 pytest-asyncio 的 function 级事件循环不兼容。
    """

    async def _setup():
        setup_engine = create_async_engine(
            settings.database_url, poolclass=NullPool
        )
        async with setup_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        await setup_engine.dispose()

    async def _teardown():
        teardown_engine = create_async_engine(
            settings.database_url, poolclass=NullPool
        )
        async with teardown_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
        await teardown_engine.dispose()

    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


# ===== Function 级: DB session + 每测后清空 =====

@pytest_asyncio.fixture
async def db_session(_create_tables) -> AsyncSession:
    """给测试代码用的 session。

    依赖 _create_tables（session 级，保证表已建好）。
    teardown 时在同一个 session 里 truncate 所有表，避免
    多连接从同一个连接池取连接导致的 asyncpg 并发冲突。
    """
    session = new_session()
    yield session
    for table in reversed(SQLModel.metadata.sorted_tables):
        await session.execute(table.delete())
    await session.commit()
    await session.close()


# ===== Function 级: Redis mock =====

@pytest_asyncio.fixture
async def fake_redis():
    """用 fakeredis 替换全局 redis_client。

    cache_get / cache_set / cache_delete_pattern 都调 get_redis()，
    get_redis() 返回 redis_client，所以只要设好 redis_client 就行。
    """
    import fakeredis
    import app.core.redis

    fake = fakeredis.FakeAsyncRedis(decode_responses=True)
    app.core.redis.redis_client = fake
    yield fake
    app.core.redis.redis_client = None
    await fake.aclose()


# ===== Function 级 autouse: arq 入队 no-op =====

@pytest.fixture(autouse=True)
def _mock_queue(monkeypatch):
    """把 arq 入队函数替换成 async no-op，避免测试连真实 Redis。

    路由模块在 import 时就把函数名绑定到了自己的命名空间，
    所以必须 patch 路由模块里的引用，而不是 app.core.queue 里的原始定义。
    """
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routers.documents.enqueue_rebuild_chunks", _noop)
    monkeypatch.setattr("app.routers.document_files.enqueue_document_job", _noop)


# ===== Function 级: 异步测试客户端 =====

@pytest_asyncio.fixture
async def app_client(db_session, fake_redis):
    """httpx AsyncClient，对应 supertest 的角色。

    ASGITransport 直接调用 ASGI app，不走真实 HTTP 端口。
    依赖 fake_redis（初始化 Redis mock），_mock_queue 是 autouse 已生效。
    lifespan 不会被 ASGITransport 触发，所以不会连真实 Redis/arq。
    """
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client


# ===== Function 级: 认证 fixture =====

@pytest_asyncio.fixture
async def test_tenant_context(db_session):
    """创建测试用户 + 租户 + OWNER 成员关系。

    返回 dict: {"user", "tenant", "token", "headers"}
    headers 可直接传给 httpx 请求的 headers 参数。
    """
    user = User(email="test@example.com", hashed_password=hash_password("Testpass123!"))
    tenant = Tenant(name="Test Tenant", slug="test-tenant")

    db_session.add(user)
    db_session.add(tenant)
    await db_session.flush()  # 拿到 user.id 和 tenant.id

    membership = TenantMembership(
        user_id=user.id, tenant_id=tenant.id, role=TenantRole.OWNER
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(tenant)

    token = create_access_token(
        user.id, tenant_id=tenant.id, role=TenantRole.OWNER.value
    )

    return {
        "user": user,
        "tenant": tenant,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest_asyncio.fixture
async def auth_headers(test_tenant_context):
    """便捷快捷方式: 只拿认证头，不关心 user/tenant 对象。"""
    return test_tenant_context["headers"]


@pytest_asyncio.fixture
async def auth_headers_no_tenant(db_session):
    """无 tid 的 token，用于测试 403（未选工作区）场景。

    创建一个用户但不关联任何租户，签发的 token 不带 tid/role claim。
    """
    user = User(email="notenant@example.com", hashed_password=hash_password("Testpass123!"))
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(user.id)  # 不传 tenant_id / role
    return {"Authorization": f"Bearer {token}"}
