"""Тесты работают на настоящем PostgreSQL (отдельная БД candles_test), LLM — заглушка, сеть не нужна."""

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://candles:candles@localhost:5432/candles_test"
)
# Глобальный engine приложения (app.db) тоже должен смотреть в тестовую БД.
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["OPENAI_API_KEY"] = ""

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from app.models import (  # noqa: E402
    Base,
    Batch,
    Material,
    Receipt,
    Recipe,
    RecipeItem,
    Role,
    Supplier,
    User,
)
from app.services.auth import hash_password  # noqa: E402
from app.services.common import Actor  # noqa: E402

SEQUENCES = ("receipt_number_seq", "batch_number_seq", "order_number_seq")


async def _ensure_database() -> None:
    dsn = TEST_DB_URL.replace("postgresql+asyncpg", "postgresql")
    base, dbname = dsn.rsplit("/", 1)
    conn = await asyncpg.connect(f"{base}/postgres")
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", dbname)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{dbname}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    asyncio.run(_ensure_database())
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    cfg.attributes["database_url"] = TEST_DB_URL
    command.upgrade(cfg, "head")


@pytest.fixture
async def engine():
    eng = create_async_engine(TEST_DB_URL, pool_size=10)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with eng.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        for seq in SEQUENCES:
            await conn.execute(text(f"ALTER SEQUENCE {seq} RESTART"))
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


@dataclass
class World:
    users: dict[str, User]
    actors: dict[str, Actor]
    wax: Material
    wick: Material
    recipe: Recipe
    supplier: Supplier
    receipt: Receipt


@pytest.fixture
async def world(session: AsyncSession) -> World:
    """Минимальный мир: 4 пользователя, 2 материала, рецепт «Лаванда» (0,5 кг воска + 1 фитиль на 1 шт)."""
    users = {
        "sklad": User(
            username="sklad",
            full_name="Петров Иван Сергеевич",
            role=Role.STOREKEEPER.value,
            password_hash=hash_password("x"),
        ),
        "tech": User(
            username="tech",
            full_name="Смирнова Анна Олеговна",
            role=Role.TECHNOLOGIST.value,
            password_hash=hash_password("x"),
        ),
        "boss": User(
            username="boss",
            full_name="Кузнецов Дмитрий Павлович",
            role=Role.MANAGER.value,
            password_hash=hash_password("x"),
        ),
        "tech2": User(
            username="tech2",
            full_name="Орлова Мария Викторовна",
            role=Role.TECHNOLOGIST.value,
            password_hash=hash_password("x"),
        ),
    }
    session.add_all(users.values())
    wax = Material(code="WAX", name="Воск соевый", unit="кг")
    wick = Material(code="WICK", name="Фитиль", unit="шт")
    supplier = Supplier(name="ООО Восковой двор")
    session.add_all([wax, wick, supplier])
    await session.flush()
    recipe = Recipe(name="Лаванда")
    recipe.items = [
        RecipeItem(material_id=wax.id, qty_per_unit=Decimal("0.5")),
        RecipeItem(material_id=wick.id, qty_per_unit=Decimal("1")),
    ]
    session.add(recipe)
    receipt = Receipt(supplier_id=supplier.id, received_date=date.today(), created_by_id=users["sklad"].id)
    session.add(receipt)
    await session.commit()
    actors = {k: Actor(u.id, u.full_name, u.role) for k, u in users.items()}
    return World(users, actors, wax, wick, recipe, supplier, receipt)


async def add_batch(
    session: AsyncSession,
    world: World,
    material: Material,
    qty: str,
    days_ago: int,
    status: str = "accepted",
    comment: str | None = None,
) -> Batch:
    day = date.today() - timedelta(days=days_ago)
    b = Batch(
        receipt_id=world.receipt.id,
        material_id=material.id,
        received_date=day,
        qty=Decimal(qty),
        remaining_qty=Decimal(qty),
        reserved_qty=Decimal(0),
        price=Decimal("100"),
        currency="RUB",
        rate=Decimal(1),
        rate_date=day,
        unit_cost_rub=Decimal("100"),
        status=status,
        comment=comment,
    )
    session.add(b)
    await session.commit()
    await session.refresh(b)
    return b
