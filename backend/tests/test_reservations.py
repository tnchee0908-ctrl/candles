"""FIFO, частичный резерв, дефицит, параллельные резервы, завершение с перерасходом и экономией."""

import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.errors import Conflict, DomainError, Forbidden
from app.models import Batch, Consumption, MarkingReport, OrderStatus, Reservation
from app.services import orders
from app.services.common import today
from tests.conftest import add_batch

TOMORROW = today() + timedelta(days=1)


async def reservations_by_batch(session, order_id, material_id=None) -> dict[int, Decimal]:
    stmt = select(Reservation).where(Reservation.order_id == order_id)
    if material_id is not None:
        stmt = stmt.where(Reservation.material_id == material_id)
    rows = await session.scalars(stmt)
    return {r.batch_id: r.qty for r in rows}


async def test_fifo_takes_oldest_batches_first(session, world):
    newest = await add_batch(session, world, world.wax, "10", days_ago=1)
    oldest = await add_batch(session, world, world.wax, "10", days_ago=30)
    middle = await add_batch(session, world, world.wax, "10", days_ago=10)
    await add_batch(session, world, world.wick, "100", days_ago=5)

    # 30 шт × 0,5 кг = 15 кг: 10 из самой старой партии и 5 из следующей по дате.
    result = await orders.create_and_plan(
        session, world.actors["tech"], recipe_id=world.recipe.id, qty=30, planned_date=TOMORROW
    )
    assert result.shortages == []
    res = await reservations_by_batch(session, result.order.id, world.wax.id)
    assert res == {oldest.id: Decimal("10"), middle.id: Decimal("5")}
    assert newest.id not in res
    assert result.order.status == OrderStatus.PLANNED


async def test_only_accepted_batches_are_reserved(session, world):
    await add_batch(session, world, world.wax, "50", days_ago=20, status="on_check")
    await add_batch(session, world, world.wax, "50", days_ago=19, status="rejected")
    accepted = await add_batch(session, world, world.wax, "4", days_ago=1)
    await add_batch(session, world, world.wick, "100", days_ago=5)

    result = await orders.create_and_plan(
        session, world.actors["tech"], recipe_id=world.recipe.id, qty=10, planned_date=TOMORROW
    )
    assert await reservations_by_batch(session, result.order.id) == {
        accepted.id: Decimal("4"),
        (await session.scalar(select(Batch.id).where(Batch.material_id == world.wick.id))): Decimal("10"),
    }
    [shortage] = result.shortages
    assert shortage.material_code == "WAX"
    assert shortage.missing == Decimal("1")  # нужно 5 кг, зарезервировано 4


async def test_partial_reserve_blocks_start_with_readable_message(session, world):
    await add_batch(session, world, world.wax, "3", days_ago=3)
    await add_batch(session, world, world.wick, "100", days_ago=3)
    result = await orders.create_and_plan(
        session, world.actors["tech"], recipe_id=world.recipe.id, qty=10, planned_date=TOMORROW
    )
    with pytest.raises(Conflict) as exc:
        await orders.start_order(session, world.actors["tech"], result.order.id)
    assert "Не хватает: 2 кг «Воск соевый»" in exc.value.message

    # Пришла новая партия — дорезервировали, теперь запускается.
    await add_batch(session, world, world.wax, "5", days_ago=0)
    replanned = await orders.plan_order(session, world.actors["tech"], result.order.id)
    assert replanned.shortages == []
    started = await orders.start_order(session, world.actors["tech"], result.order.id)
    assert started.status == OrderStatus.IN_PROGRESS


async def test_parallel_reservations_do_not_share_stock(session_factory, world):
    async with session_factory() as s:
        await add_batch(s, world, world.wax, "10", days_ago=5)
        await add_batch(s, world, world.wax, "10", days_ago=4)
        await add_batch(s, world, world.wick, "1000", days_ago=4)
        # Два черновика по 30 шт (15 кг каждый) при остатке 20 кг.
        o1 = await orders.create_order(
            s, world.actors["tech"], recipe_id=world.recipe.id, qty=30, planned_date=TOMORROW
        )
        o2 = await orders.create_order(
            s, world.actors["boss"], recipe_id=world.recipe.id, qty=30, planned_date=TOMORROW
        )
        await s.commit()

    async def plan(order_id, actor):
        async with session_factory() as s:
            return await orders.plan_order(s, actor, order_id)

    r1, r2 = await asyncio.gather(plan(o1.id, world.actors["tech"]), plan(o2.id, world.actors["boss"]))

    async with session_factory() as s:
        total_reserved = await s.scalar(
            select(func.sum(Reservation.qty)).where(Reservation.material_id == world.wax.id)
        )
        assert total_reserved == Decimal("20")
        for b in await s.scalars(select(Batch).where(Batch.material_id == world.wax.id)):
            assert b.reserved_qty <= b.remaining_qty
            assert b.reserved_qty == b.qty  # обе партии выбраны полностью, но не сверх остатка
    missing = sorted(sum((s.missing for s in r.shortages), Decimal(0)) for r in (r1, r2))
    assert missing == [Decimal("0"), Decimal("10")]  # один получил 15, другой — оставшиеся 5


async def test_complete_writes_off_overrun_and_returns_savings(session, world):
    b1 = await add_batch(session, world, world.wax, "10", days_ago=10)
    b2 = await add_batch(session, world, world.wax, "10", days_ago=5)
    wick = await add_batch(session, world, world.wick, "100", days_ago=5)
    result = await orders.create_and_plan(
        session, world.actors["tech"], recipe_id=world.recipe.id, qty=10, planned_date=TOMORROW
    )  # 5 кг воска, 10 фитилей
    await orders.start_order(session, world.actors["tech"], result.order.id)

    # Воска ушло больше (перерасход 7 − 5 = 2), фитилей меньше (экономия 10 − 8 = 2).
    await orders.complete_order(
        session,
        world.actors["tech"],
        result.order.id,
        {world.wax.id: Decimal("7"), world.wick.id: Decimal("8")},
    )

    batches = {
        b.id: b for b in await session.scalars(select(Batch).execution_options(populate_existing=True))
    }
    assert batches[b1.id].remaining_qty == Decimal("3")  # 5 по резерву + 2 перерасхода — всё из старой
    assert batches[b2.id].remaining_qty == Decimal("10")
    assert batches[wick.id].remaining_qty == Decimal("92")  # экономия вернулась в партию
    assert all(b.reserved_qty == 0 for b in batches.values())
    consumed = await session.scalar(
        select(func.sum(Consumption.qty)).where(Consumption.material_id == world.wax.id)
    )
    assert consumed == Decimal("7")
    report = await session.scalar(select(MarkingReport).where(MarkingReport.order_id == result.order.id))
    assert report is not None and report.status == "pending"


async def test_overrun_without_stock_is_a_readable_error(session, world):
    await add_batch(session, world, world.wax, "5", days_ago=10)
    await add_batch(session, world, world.wick, "100", days_ago=5)
    result = await orders.create_and_plan(
        session, world.actors["tech"], recipe_id=world.recipe.id, qty=10, planned_date=TOMORROW
    )
    await orders.start_order(session, world.actors["tech"], result.order.id)
    with pytest.raises(DomainError) as exc:
        await orders.complete_order(
            session,
            world.actors["tech"],
            result.order.id,
            {world.wax.id: Decimal("7.5"), world.wick.id: Decimal("10")},
        )
    assert exc.value.message.startswith("Не хватает 2,5 кг «Воск соевый»")


async def test_cancel_releases_reservation_and_only_before_start(session, world):
    batch = await add_batch(session, world, world.wax, "10", days_ago=10)
    await add_batch(session, world, world.wick, "100", days_ago=5)
    result = await orders.create_and_plan(
        session, world.actors["tech"], recipe_id=world.recipe.id, qty=4, planned_date=TOMORROW
    )
    await orders.cancel_order(session, world.actors["tech"], result.order.id)
    await session.refresh(batch)
    assert batch.reserved_qty == 0

    other = await orders.create_and_plan(
        session, world.actors["tech"], recipe_id=world.recipe.id, qty=4, planned_date=TOMORROW
    )
    await orders.start_order(session, world.actors["tech"], other.order.id)
    with pytest.raises(Conflict):
        await orders.cancel_order(session, world.actors["tech"], other.order.id)


async def test_storekeeper_cannot_plan_orders(session, world):
    with pytest.raises(Forbidden):
        await orders.create_and_plan(
            session, world.actors["sklad"], recipe_id=world.recipe.id, qty=1, planned_date=TOMORROW
        )
