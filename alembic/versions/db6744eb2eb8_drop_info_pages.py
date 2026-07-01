"""drop info_pages table

Revision ID: db6744eb2eb8
Revises: 13b89dac497d
Create Date: 2026-06-26 12:27:06.282623

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "db6744eb2eb8"
down_revision: Union[str, Sequence[str], None] = "13b89dac497d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF EXISTS — на чистой БД таблица могла никогда не существовать
    op.execute("DROP INDEX IF EXISTS ix_info_pages_slug")
    op.execute("DROP TABLE IF EXISTS info_pages")


def downgrade() -> None:
    op.create_table(
        "info_pages",
        sa.Column("slug", sa.VARCHAR(length=100), autoincrement=False, nullable=False),
        sa.Column("title", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column("content", sa.TEXT(), autoincrement=False, nullable=False),
        sa.Column(
            "footer_group", sa.VARCHAR(length=50), autoincrement=False, nullable=True
        ),
        sa.Column("position", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("is_published", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("info_pages_pkey")),
    )
    op.create_index(op.f("ix_info_pages_slug"), "info_pages", ["slug"], unique=True)
