"""add document processing_status and error_message

Revision ID: a1b2c3d4e5f6
Revises: d2bb94e3f1ca
Create Date: 2026-09-24 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'd2bb94e3f1ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Document 表加两列：
      - processing_status: 复用 extractionstatus 枚举类型，默认 'SUCCESS'
      - error_message: text, nullable

    复用已有 enum 类型 extractionstatus（documentfile 表已建），
    不需要新建类型，列直接挂上去即可。
    """
    # 加 processing_status 列，挂到已有的 extractionstatus enum
    # server_default 用 'SUCCESS' 给所有旧行赋值，避免 NOT NULL 报错
    op.add_column(
        'document',
        sa.Column(
            'processing_status',
            sa.Enum('PENDING', 'PROCESSING', 'SUCCESS', 'FAILED', name='extractionstatus'),
            nullable=False,
            server_default='SUCCESS',
        ),
    )
    op.create_index('ix_document_processing_status', 'document', ['processing_status'])

    # 加 error_message 列
    op.add_column(
        'document',
        sa.Column('error_message', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('document', 'error_message')
    op.drop_index('ix_document_processing_status', table_name='document')
    op.drop_column('document', 'processing_status')
