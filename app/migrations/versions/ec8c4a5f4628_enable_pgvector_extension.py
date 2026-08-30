"""enable pgvector extension

Revision ID: ec8c4a5f4628
Revises: 2b48a86c2faa
Create Date: 2026-08-30 05:07:23.475099

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'ec8c4a5f4628'
down_revision: Union[str, Sequence[str], None] = '2b48a86c2faa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")