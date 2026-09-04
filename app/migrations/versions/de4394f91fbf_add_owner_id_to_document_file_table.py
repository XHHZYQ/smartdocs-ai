"""add owner_id to document_file table

Revision ID: de4394f91fbf
Revises: 09a1322e0899
Create Date: 2026-09-04 16:47:07.342065

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'de4394f91fbf'
down_revision: Union[str, Sequence[str], None] = '09a1322e0899'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documentfile",
        sa.Column("owner_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_documentfile_owner_id_user",
        "documentfile", "user",
        ["owner_id"], ["id"],
    )
    op.create_index(
        op.f("ix_documentfile_owner_id"), "documentfile", ["owner_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_documentfile_owner_id"), table_name="documentfile")
    op.drop_constraint("fk_documentfile_owner_id_user", "documentfile", type_="foreignkey")
    op.drop_column("documentfile", "owner_id")
