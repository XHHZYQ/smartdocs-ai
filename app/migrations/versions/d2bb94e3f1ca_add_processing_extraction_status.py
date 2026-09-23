"""add processing extraction status

Revision ID: d2bb94e3f1ca
Revises: 8c02509226fc
Create Date: 2026-09-23 15:16:45.004143

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'd2bb94e3f1ca'
down_revision: Union[str, Sequence[str], None] = '8c02509226fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # PostgreSQL 规定 ALTER TYPE ... ADD VALUE 不能在事务块中执行，
    # 而 Alembic 默认把迁移包在事务里，必须切到 autocommit 模式
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE extractionstatus ADD VALUE 'PROCESSING'")


def downgrade() -> None:
    """Downgrade schema.

    PostgreSQL 没有移除枚举值的直接语法，标准做法是"重建类型"：
    1. 先把使用 PROCESSING 的行退回 PENDING（旧版代码不认识 PROCESSING）
    2. rename 旧类型 → 建新类型(不含 PROCESSING) → 列转挂新类型 → 删旧类型
    """
    op.execute(
        "UPDATE documentfile SET extraction_status = 'PENDING' "
        "WHERE extraction_status::text = 'PROCESSING'"
    )
    op.execute("ALTER TYPE extractionstatus RENAME TO extractionstatus_old")
    op.execute(
        "CREATE TYPE extractionstatus AS ENUM ('PENDING', 'SUCCESS', 'FAILED')"
    )
    op.execute(
        "ALTER TABLE documentfile "
        "ALTER COLUMN extraction_status TYPE extractionstatus "
        "USING extraction_status::text::extractionstatus"
    )
    op.execute("DROP TYPE extractionstatus_old")
