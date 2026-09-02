"""add hnsw index on chunk embedding

Revision ID: 09a1322e0899
Revises: e8a104fb7ac9
Create Date: 2026-09-02 10:04:31.117207

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '09a1322e0899'
down_revision: Union[str, Sequence[str], None] = 'e8a104fb7ac9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ix_chunk_embedding_hnsw "
        "ON chunk USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw")
