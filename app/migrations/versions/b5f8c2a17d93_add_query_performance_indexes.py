"""add query performance indexes

Revision ID: b5f8c2a17d93
Revises: a1b2c3d4e5f6
Create Date: 2026-10-15 10:00:00.000000

1. document 列表查询 WHERE tenant_id = ? ORDER BY created_at DESC：
   建 (tenant_id, created_at DESC) 复合索引，删掉被最左前缀覆盖的
   ix_document_tenant_id 单列索引
2. chunk 向量检索 ORDER BY embedding <=> ?（cosine 距离）：
   建 HNSW 索引（vector_cosine_ops），消除全表精确扫描
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5f8c2a17d93"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. document 复合索引。先建新索引再删旧索引，
    # 中间任何时刻 tenant_id 查询都有索引可用
    op.create_index(
        "ix_document_tenant_created_at",
        "document",
        ["tenant_id", sa.text("created_at DESC")],
    )
    op.drop_index("ix_document_tenant_id", table_name="document")

    # 2. chunk 向量 ANN 索引。
    # postgresql_ops 必须和检索语句的距离算子匹配：
    # cosine_distance() 生成 embedding <=> ?，对应 vector_cosine_ops
    # （若用 L2 距离 <-> 则是 vector_l2_ops，配错则优化器不走索引）
    op.create_index(
        "ix_chunk_embedding_hnsw",
        "chunk",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_chunk_embedding_hnsw", table_name="chunk")
    # 恢复 tenant_id 单列索引后再删复合索引，保证回滚各阶段都有索引可用
    op.create_index("ix_document_tenant_id", "document", ["tenant_id"])
    op.drop_index("ix_document_tenant_created_at", table_name="document")
