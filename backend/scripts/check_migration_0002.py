"""Проверка миграции 0002 на «старой» базе: задание «В работе» с несписанным резервом.

Запуск: docker compose run --rm tests python scripts/check_migration_0002.py
Создаёт временную БД candles_migration_check, поднимает её до 0001, кладёт данные по старой схеме,
поднимает до 0002 и проверяет, что резерв запущенного задания стал списанием. БД потом удаляется.
"""

import asyncio
import os

import asyncpg

from alembic import command
from alembic.config import Config

BASE = os.environ.get("TEST_DATABASE_URL", "postgresql+asyncpg://candles:candles@db:5432/candles_test")
SERVER = BASE.replace("postgresql+asyncpg", "postgresql").rsplit("/", 1)[0]
DB = "candles_migration_check"
URL = f"{BASE.rsplit('/', 1)[0]}/{DB}"


def alembic(rev: str) -> None:
    cfg = Config("alembic.ini")
    cfg.attributes["database_url"] = URL
    command.upgrade(cfg, rev)


async def main() -> None:
    admin = await asyncpg.connect(f"{SERVER}/postgres")
    await admin.execute(f'DROP DATABASE IF EXISTS "{DB}"')
    await admin.execute(f'CREATE DATABASE "{DB}"')
    await admin.close()
    try:
        await asyncio.to_thread(alembic, "0001")
        conn = await asyncpg.connect(f"{SERVER}/{DB}")
        await conn.execute(
            """
            INSERT INTO users (id, username, full_name, role, password_hash) VALUES (1, 'tech', 'Т', 'technologist', 'x');
            INSERT INTO materials (id, code, name, unit) VALUES (1, 'WAX', 'Воск', 'кг');
            INSERT INTO suppliers (id, name) VALUES (1, 'ООО Тест');
            INSERT INTO receipts (id, supplier_id, received_date, created_by_id) VALUES (1, 1, '2026-10-01', 1);
            INSERT INTO batches (id, receipt_id, material_id, received_date, qty, remaining_qty, reserved_qty,
                                 price, currency, rate, rate_date, unit_cost_rub, status)
                 VALUES (1, 1, 1, '2026-10-01', 10, 10, 7, 100, 'RUB', 1, '2026-10-01', 100, 'accepted');
            INSERT INTO recipes (id, name) VALUES (1, 'Лаванда');
            INSERT INTO production_orders (id, recipe_id, qty, planned_date, status, created_by_id, started_at)
                 VALUES (1, 1, 6, '2026-10-02', 'in_progress', 1, '2026-10-02 09:00+00'),
                        (2, 1, 2, '2026-10-20', 'planned', 1, NULL);
            INSERT INTO order_components (order_id, material_id, required_qty, reserved_qty)
                 VALUES (1, 1, 6, 6), (2, 1, 1, 1);
            INSERT INTO reservations (order_id, batch_id, material_id, qty) VALUES (1, 1, 1, 6), (2, 1, 1, 1);
            """
        )
        await conn.close()
        await asyncio.to_thread(alembic, "0002")
        conn = await asyncpg.connect(f"{SERVER}/{DB}")
        batch = await conn.fetchrow("SELECT remaining_qty, reserved_qty FROM batches WHERE id = 1")
        reservations = await conn.fetch("SELECT order_id, qty FROM reservations ORDER BY order_id")
        consumed = await conn.fetch("SELECT order_id, qty, consumed_at FROM consumptions")
        await conn.close()
        assert (batch["remaining_qty"], batch["reserved_qty"]) == (4, 1), dict(batch)
        assert [(r["order_id"], r["qty"]) for r in reservations] == [(2, 1)]  # запланированное не тронуто
        assert [(c["order_id"], c["qty"]) for c in consumed] == [(1, 6)]
        print("миграция 0002: OK — резерв запущенного задания стал выдачей в цех, остальное не тронуто")
    finally:
        admin = await asyncpg.connect(f"{SERVER}/postgres")
        await admin.execute(f'DROP DATABASE IF EXISTS "{DB}"')
        await admin.close()


asyncio.run(main())
