"""测试 app.services.retrieval.retrieve_chunks —— pgvector 余弦检索 + 租户隔离。

需要测试数据库（smartdocs_test，含 pgvector 扩展）。
get_embeddings 用 monkeypatch 替换成确定性向量，避免真实 API 调用；
向量维度固定为 settings.embedding_dimensions（1024）。

向量设计：查询向量固定 [1, 0, 0, ...]，
- embedding 首位 = 1.0 → 余弦距离 0（完全一致）
- embedding 首位 = 0.0 → 余弦距离 1（正交）
"""
import math

import pytest_asyncio

from app.core.config import settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.models.tenant import Tenant
from app.services.retrieval import retrieve_chunks

DIM = settings.embedding_dimensions


def vec(first: float) -> list[float]:
    return [first] + [0.0] * (DIM - 1)


QUERY_VECTOR = vec(1.0)


@pytest_asyncio.fixture
async def seeded(db_session, test_tenant_context, monkeypatch):
    """两个租户、两份文档、三个 chunk：
    - near:  本租户，距离 0
    - far:   本租户，距离 1
    - foreign: 其他租户，距离 0（隔离用，不应出现在结果里）
    """
    from app.core.security import hash_password
    from app.models.user import User

    tenant = test_tenant_context["tenant"]
    user = test_tenant_context["user"]

    doc = Document(owner_id=user.id, tenant_id=tenant.id, title="检索测试文档")
    other_tenant = Tenant(name="Other Tenant", slug="other-tenant")
    other_user = User(email="other@example.com", hashed_password=hash_password("Testpass123!"))
    db_session.add_all([doc, other_tenant, other_user])
    await db_session.flush()

    other_doc = Document(owner_id=other_user.id, tenant_id=other_tenant.id, title="别家文档")
    db_session.add(other_doc)
    await db_session.flush()

    near = Chunk(tenant_id=tenant.id, document_id=doc.id, chunk_index=0,
                 content="最近的块", char_count=4, embedding=vec(1.0))
    far = Chunk(tenant_id=tenant.id, document_id=doc.id, chunk_index=1,
                content="较远的块", char_count=4, embedding=vec(0.0))
    foreign = Chunk(tenant_id=other_tenant.id, document_id=other_doc.id, chunk_index=0,
                    content="别家租户的块", char_count=6, embedding=vec(1.0))
    db_session.add_all([near, far, foreign])
    await db_session.commit()
    await db_session.refresh(near)
    await db_session.refresh(far)
    await db_session.refresh(foreign)

    async def _fake_embeddings(texts: list[str]) -> list[list[float]]:
        assert texts == ["测试查询"]
        return [QUERY_VECTOR]

    monkeypatch.setattr("app.services.retrieval.get_embeddings", _fake_embeddings)

    return {"tenant": tenant, "doc": doc, "near": near, "far": far, "foreign": foreign}


class TestRetrieveChunks:
    async def test_orders_by_distance(self, db_session, seeded):
        results = await retrieve_chunks(db_session, seeded["tenant"].id, "测试查询", top_k=5)

        assert [row[0].id for row in results] == [seeded["near"].id, seeded["far"].id]

    async def test_row_shape(self, db_session, seeded):
        """返回 (Chunk, document_title, distance) 三元组。"""
        results = await retrieve_chunks(db_session, seeded["tenant"].id, "测试查询", top_k=5)

        chunk, title, distance = results[0]
        assert chunk.id == seeded["near"].id
        assert title == "检索测试文档"
        assert math.isclose(distance, 0.0, abs_tol=1e-6)

    async def test_tenant_isolation(self, db_session, seeded):
        """其他租户的 chunk 永远不可见，即使向量距离更近。"""
        results = await retrieve_chunks(db_session, seeded["tenant"].id, "测试查询", top_k=10)

        ids = [row[0].id for row in results]
        assert seeded["foreign"].id not in ids

    async def test_top_k_limit(self, db_session, seeded):
        results = await retrieve_chunks(db_session, seeded["tenant"].id, "测试查询", top_k=1)

        assert len(results) == 1
        assert results[0][0].id == seeded["near"].id
