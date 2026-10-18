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

    # Запуск задания теперь выдаёт материал в цех (резерв списывается). Задания, запущенные
    # до этой версии, переводим на новую схему: их резерв становится списанием на дату запуска.
    op.execute(
        """
        INSERT INTO consumptions (order_id, batch_id, material_id, qty, unit_cost_rub, consumed_at)
        SELECT r.order_id, r.batch_id, r.material_id, r.qty, b.unit_cost_rub, COALESCE(o.started_at, now())
        FROM reservations r
        JOIN batches b ON b.id = r.batch_id
        JOIN production_orders o ON o.id = r.order_id
        WHERE o.status = 'in_progress'
        """
    )
    op.execute(
        """
        UPDATE batches b
        SET remaining_qty = b.remaining_qty - s.qty, reserved_qty = b.reserved_qty - s.qty
        FROM (
            SELECT r.batch_id, sum(r.qty) AS qty
            FROM reservations r JOIN production_orders o ON o.id = r.order_id
            WHERE o.status = 'in_progress'
            GROUP BY r.batch_id
        ) s
        WHERE b.id = s.batch_id
        """
    )
    op.execute(
        """
        DELETE FROM reservations r USING production_orders o
        WHERE o.id = r.order_id AND o.status = 'in_progress'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_login_failures_at", table_name="login_failures")
    op.drop_table("login_failures")
    op.drop_column("suppliers", "aliases")
