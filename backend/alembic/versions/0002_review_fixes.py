"""review fixes: supplier spelling variants

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


def downgrade() -> None:
    op.drop_column("suppliers", "aliases")
