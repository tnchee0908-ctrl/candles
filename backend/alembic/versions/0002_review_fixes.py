"""review fixes: supplier spelling variants, login failures

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18 10:00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Другие написания названия поставщика («Арома Трейд» для Aroma Trade GmbH): один поставщик —
    # один псевдоним при любом написании.
    op.add_column(
        "suppliers",
        sa.Column("aliases", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    # Неудачные входы — для ограничения перебора паролей.
    op.create_table(
        "login_failures",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_login_failures_at", "login_failures", ["at"])


def downgrade() -> None:
    op.drop_index("ix_login_failures_at", table_name="login_failures")
    op.drop_table("login_failures")
    op.drop_column("suppliers", "aliases")
