"""Учёт: выдача в цех при запуске, сверка при завершении, конкурентность и граничные случаи.

Часть тестов написана под конкретные «мутанты» из ревью: если в коде снять блокировку, перечитывание
партий или поменять округление — эти тесты падают.
"""

import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.errors import DomainError
from app.models import AuditLog, Batch, Consumption, OrderStatus, Reservation
from app.services import batches, orders, reports
from app.services.batches import BatchFilters
from app.services.common import q_money, today
from tests.conftest import add_batch

TOMORROW = today() + timedelta(days=1)


async def assert_batches_consistent(session) -> None:
    """Инварианты партии: резерв = сумма резервов заданий; списано = qty − остаток."""
    for b in await session.scalars(select(Batch).execution_options(populate_existing=True)):
        reserved = await session.scalar(
            select(func.coalesce(func.sum(Reservation.qty), 0)).where(Reservation.batch_id == b.id)
        )
        consumed = await session.scalar(
            select(func.coalesce(func.sum(Consumption.qty), 0)).where(Consumption.batch_id == b.id)
        )
        assert b.reserved_qty == reserved, f"{b.number}: резерв {b.reserved_qty} ≠ {reserved}"
        assert b.qty - b.remaining_qty == consumed, (
            f"{b.number}: списано {consumed}, остаток {b.remaining_qty}"
        )
        assert 0 <= b.reserved_qty <= b.remaining_qty


# ---------- N2: выдача в цех и сверка ----------


async def test_start_writes_off_reserve_and_stock_drops(session, world):
    b = await add_batch(session, world, world.wax, "10", days_ago=3)
    await add_batch(session, world, world.wick, "100", days_ago=3)
    tech = world.actors["tech"]
    planned = await orders.create_and_plan(
        session, tech, recipe_id=world.recipe.id, qty=4, planned_date=TOMORROW
    )
    before = (await reports.material_stock(session, tech, "WAX"))[0]
    assert before["on_hand"] == Decimal("10") and before["reserved"] == Decimal("2")

    await orders.start_order(session, tech, planned.order.id)
    after = (await reports.material_stock(session, tech, "WAX"))[0]
    # Материал выдан в цех: на складе его больше нет, в резерве тоже.
    assert after["on_hand"] == Decimal("8") and after["reserved"] == Decimal("0")
    await session.refresh(b)
    assert b.remaining_qty == Decimal("8") and b.reserved_qty == 0
    assert await session.scalar(select(func.count()).select_from(Reservation)) == 0
    cost = await reports.order_cost(session, tech, planned.order.number)
    assert cost["basis"] == "материал, выданный в цех" and cost["complete"] is True
    await assert_batches_consistent(session)


async def test_savings_return_to_newest_issued_batch_first(session, world):
    old = await add_batch(session, world, world.wax, "3", days_ago=10)
    new = await add_batch(session, world, world.wax, "10", days_ago=1)
    await add_batch(session, world, world.wick, "100", days_ago=3)
    tech = world.actors["tech"]
    planned = await orders.create_and_plan(
        session, tech, recipe_id=world.recipe.id, qty=10, planned_date=TOMORROW
    )
    await orders.start_order(session, tech, planned.order.id)  # 5 кг: 3 из старой + 2 из новой
    await orders.complete_order(
        session, tech, planned.order.id, {world.wax.id: Decimal("4"), world.wick.id: Decimal("10")}
    )
    await session.refresh(old)
    await session.refresh(new)
    assert old.remaining_qty == 0  # старая партия так и ушла целиком
    assert new.remaining_qty == Decimal("9")  # 1 кг экономии вернулся в новую
    await assert_batches_consistent(session)


# ---------- S9: мутанты ----------


async def test_two_parallel_plans_of_one_draft_reserve_once(session_factory, world):
    """Мутант: без блокировки строки задания оба «Запланировать» зарезервировали бы дважды."""
    async with session_factory() as s:
        await add_batch(s, world, world.wax, "20", days_ago=3)
        await add_batch(s, world, world.wick, "100", days_ago=3)
        draft = await orders.create_order(
            s, world.actors["tech"], recipe_id=world.recipe.id, qty=10, planned_date=TOMORROW
        )
        await s.commit()

    async def plan():
        async with session_factory() as s:
            await orders.plan_order(s, world.actors["tech"], draft.id)

    await asyncio.gather(plan(), plan())
    async with session_factory() as s:
        reserved = await s.scalar(
            select(func.sum(Reservation.qty)).where(
                Reservation.order_id == draft.id, Reservation.material_id == world.wax.id
            )
        )
        assert reserved == Decimal("5")
        await assert_batches_consistent(s)


async def test_planning_rereads_batches_after_lock(session_factory, world):
    """Мутант: без перечитывания партий после FOR UPDATE сессия взяла бы устаревший резерв из памяти."""
    async with session_factory() as s:
        await add_batch(s, world, world.wax, "20", days_ago=3)
        await add_batch(s, world, world.wick, "100", days_ago=3)
        o1 = await orders.create_order(
            s, world.actors["tech"], recipe_id=world.recipe.id, qty=30, planned_date=TOMORROW
        )
        o2 = await orders.create_order(
            s, world.actors["tech"], recipe_id=world.recipe.id, qty=30, planned_date=TOMORROW
        )
        await s.commit()

    async with session_factory() as stale:
        cached = list(await stale.scalars(select(Batch)))  # партии в памяти сессии с резервом 0
        async with session_factory() as other:
            await orders.plan_order(other, world.actors["tech"], o1.id)  # зарезервировал 15 из 20
        result = await orders.plan_order(stale, world.actors["tech"], o2.id)
        assert sum((x.missing for x in result.shortages), Decimal(0)) == Decimal("10")  # досталось 5
        assert cached  # держим ссылки: иначе сессия забудет объекты и перечитает их сама
    async with session_factory() as s:
        await assert_batches_consistent(s)


async def test_rereserve_adds_to_existing_reservation(session, world):
    """Мутант: дорезерв из той же партии перезаписывал бы количество вместо добавления."""
    b = await add_batch(session, world, world.wax, "10", days_ago=3)
    await add_batch(session, world, world.wick, "100", days_ago=3)
    tech = world.actors["tech"]
    blocker = await orders.create_and_plan(
        session, tech, recipe_id=world.recipe.id, qty=16, planned_date=TOMORROW
    )
    target = await orders.create_and_plan(
        session, tech, recipe_id=world.recipe.id, qty=10, planned_date=TOMORROW
    )
    assert target.shortages[0].missing == Decimal("3")  # из 10 кг 8 заняты, взяли 2
    await orders.cancel_order(session, tech, blocker.order.id)
    await orders.plan_order(session, tech, target.order.id)  # ещё 3 кг из той же партии
    row = await session.scalar(
        select(Reservation).where(Reservation.order_id == target.order.id, Reservation.batch_id == b.id)
    )
    assert row.qty == Decimal("5")
    await assert_batches_consistent(session)


async def test_parallel_overruns_do_not_oversell_free_stock(session_factory, world):
    """Мутант: без блокировки партий два перерасхода списали бы один и тот же свободный остаток.

    Задания выданы из РАЗНЫХ партий, а перерасход берут из одной общей — их выстраивает в очередь
    только блокировка этой общей партии.
    """
    async with session_factory() as s:
        await add_batch(s, world, world.wax, "1", days_ago=9)  # под первое задание
        await add_batch(s, world, world.wax, "1", days_ago=8)  # под второе
        await add_batch(s, world, world.wax, "3", days_ago=1)  # общий свободный остаток
        tech = world.actors["tech"]
        ids = []
        for days in (7, 6):
            await add_batch(s, world, world.wick, "2", days_ago=days)  # свои фитили у каждого
            r = await orders.create_and_plan(s, tech, recipe_id=world.recipe.id, qty=2, planned_date=TOMORROW)
            ids.append(r.order.id)
        for order_id in ids:
            await orders.start_order(s, tech, order_id)

    # Барьер сразу после чтения свободного остатка: без блокировки обе транзакции прочитают одно и то же
    # и обе спишут; с блокировкой вторая ждёт в базе и до барьера не доходит (барьер отпускает по таймауту).
    barrier = asyncio.Barrier(2)

    async def complete(order_id):
        async with session_factory() as s:
            original = s.scalars

            async def scalars(stmt, *args, **kwargs):
                result = await original(stmt, *args, **kwargs)
                sql = str(stmt)
                if "remaining_qty >" in sql and "consumptions" not in sql:
                    rows = list(result)
                    try:
                        await asyncio.wait_for(barrier.wait(), 1)
                    except (TimeoutError, asyncio.BrokenBarrierError):
                        pass
                    return iter(rows)
                return result

            s.scalars = scalars  # type: ignore[method-assign]
            try:
                await orders.complete_order(
                    s,
                    world.actors["tech"],
                    order_id,
                    {world.wax.id: Decimal("3"), world.wick.id: Decimal("2")},
                )
                return "ok"
            except DomainError:
                return "short"

    results = sorted(await asyncio.gather(*(complete(i) for i in ids)))
    async with session_factory() as s:
        await assert_batches_consistent(s)
    assert results == ["ok", "short"]  # на двоих 4 кг перерасхода, свободно только 3


async def test_accepted_batch_cannot_become_rejected(session, world):
    b = await add_batch(session, world, world.wax, "5", days_ago=1, status="on_check")
    await batches.set_status(session, world.actors["sklad"], b.id, "accepted")
    with pytest.raises(DomainError, match="нельзя перевести"):
        await batches.set_status(session, world.actors["sklad"], b.id, "rejected")


def test_money_rounds_half_up():
    assert q_money(Decimal("0.125")) == Decimal("0.13")
    assert q_money(Decimal("2.675")) == Decimal("2.68")
    assert q_money(Decimal("-0.125")) == Decimal("-0.13")


async def test_agent_step_limit_stops_endless_tool_calls(session, session_factory, world):
    from app.assistant.chat import ChatService
    from app.assistant.llm.router import FallbackLLM
    from app.config import get_settings
    from app.models import Conversation, Message
    from tests.fakes import ScriptedProvider, call

    limit = get_settings().llm_max_tool_steps
    provider = ScriptedProvider("fake", [call("list_recipes", {}) for _ in range(limit + 5)])
    chat = ChatService(FallbackLLM([provider]), session_factory)
    conv = Conversation(user_id=world.users["tech"].id)
    session.add(conv)
    await session.commit()

    async def emit(_):
        return None

    msg_id = await chat.run_turn(
        user=world.users["tech"],
        conversation_id=conv.id,
        text="?",
        file_ids=[],
        emit=emit,
        stop=asyncio.Event(),
    )
    assert len(provider.requests) == limit
    assert "Слишком много шагов" in (await session.get(Message, msg_id)).content


# ---------- граничные случаи из ревью ----------


async def test_fractional_pieces_are_rejected(session, world):
    await add_batch(session, world, world.wax, "10", days_ago=3)
    await add_batch(session, world, world.wick, "100", days_ago=3)
    tech = world.actors["tech"]
    planned = await orders.create_and_plan(
        session, tech, recipe_id=world.recipe.id, qty=2, planned_date=TOMORROW
    )
    await orders.start_order(session, tech, planned.order.id)
    with pytest.raises(DomainError, match="целое число"):
        await orders.complete_order(
            session, tech, planned.order.id, {world.wax.id: Decimal("1"), world.wick.id: Decimal("0.5")}
        )


async def test_past_dated_draft_cannot_be_planned(session, world):
    from app.models import ProductionOrder

    await add_batch(session, world, world.wick, "100", days_ago=3)
    tech = world.actors["tech"]
    draft = await orders.create_order(session, tech, recipe_id=world.recipe.id, qty=2, planned_date=TOMORROW)
    await session.commit()
    order = await session.get(ProductionOrder, draft.id)
    order.planned_date = today() - timedelta(days=3)  # черновик «пролежал» три дня
    await session.commit()
    with pytest.raises(DomainError, match="уже прошла"):
        await orders.plan_order(session, tech, draft.id)


async def test_rejected_and_unchecked_batches_have_no_free_stock(session, world):
    from app.api.converters import batch_row

    rejected = await add_batch(session, world, world.wax, "300", days_ago=3, status="rejected")
    unchecked = await add_batch(session, world, world.wax, "25", days_ago=1, status="on_check")
    rows, _ = await batches.list_batches(
        session, world.actors["boss"], BatchFilters(), sort="free_qty", direction="desc"
    )
    free = {b.id: batch_row(b, m, s).free_qty for b, m, s in rows}
    assert free[rejected.id] == 0 and free[unchecked.id] == 0
    assert batches.free_qty(rejected) == 0


async def test_price_sort_compares_in_rubles(session, world):
    usd_4500 = await add_batch(session, world, world.wax, "1", days_ago=2)
    rub_600 = await add_batch(session, world, world.wax, "1", days_ago=1)
    usd_4500.price, usd_4500.currency, usd_4500.rate = Decimal("50"), "USD", Decimal("90")  # 4500 ₽
    rub_600.price, rub_600.rate = Decimal("600"), Decimal("1")  # 600 ₽
    await session.commit()
    rows, _ = await batches.list_batches(
        session, world.actors["boss"], BatchFilters(), sort="price", direction="desc"
    )
    assert [b.id for b, _, _ in rows] == [usd_4500.id, rub_600.id]


async def test_order_cost_total_equals_sum_of_lines(session, world):
    b = await add_batch(session, world, world.wax, "10", days_ago=3)
    w = await add_batch(session, world, world.wick, "100", days_ago=3)
    b.unit_cost_rub, w.unit_cost_rub = Decimal("333.333333"), Decimal("1.005005")
    await session.commit()
    tech = world.actors["tech"]
    planned = await orders.create_and_plan(
        session, tech, recipe_id=world.recipe.id, qty=3, planned_date=TOMORROW
    )
    cost = await reports.order_cost(session, tech, planned.order.number)
    assert cost["total_cost_rub"] == sum(line["cost_rub"] for line in cost["lines"])


async def test_batch_creation_is_audited_with_rate_and_cost(session, world):
    from app.services.batches import ReceiptLine

    class Rates:
        async def fetch(self, currency, on_date):
            return Decimal("91.5")

    receipt = await batches.create_receipt(
        session,
        world.actors["sklad"],
        supplier_name="ООО Восковой двор",
        received_date=today(),
        lines=[ReceiptLine("WAX", Decimal("2"), Decimal("10"), "USD")],
        rates_client=Rates(),  # type: ignore[arg-type]
    )
    entry = await session.scalar(
        select(AuditLog).where(AuditLog.entity_type == "batch", AuditLog.action == "Партия создана")
    )
    assert receipt and {"rate", "rate_date", "unit_cost_rub"} <= set(entry.after)


async def test_weeks_without_consumption_are_zero(session, world):
    await add_batch(session, world, world.wax, "10", days_ago=3)
    await add_batch(session, world, world.wick, "100", days_ago=3)
    tech = world.actors["tech"]
    planned = await orders.create_and_plan(
        session, tech, recipe_id=world.recipe.id, qty=2, planned_date=TOMORROW
    )
    await orders.start_order(session, tech, planned.order.id)
    rows = await reports.consumption_by_week(
        session, world.actors["boss"], today() - timedelta(days=27), today(), "WAX"
    )
    weeks = sorted({r["week_start"] for r in rows})
    assert len(weeks) >= 4  # четыре недели, даже если расход был только в последнюю
    assert [r["qty"] for r in rows if r["qty"] == 0]


async def test_storekeeper_does_not_see_marking_log_in_order_card(session, world):
    from app.api.orders import build_card

    await add_batch(session, world, world.wax, "10", days_ago=3)
    await add_batch(session, world, world.wick, "100", days_ago=3)
    tech = world.actors["tech"]
    planned = await orders.create_and_plan(
        session, tech, recipe_id=world.recipe.id, qty=2, planned_date=TOMORROW
    )
    await orders.start_order(session, tech, planned.order.id)
    await orders.complete_order(
        session, tech, planned.order.id, {world.wax.id: Decimal("1"), world.wick.id: Decimal("2")}
    )
    assert (await build_card(session, planned.order.id, tech)).marking is not None
    assert (await build_card(session, planned.order.id, world.actors["sklad"])).marking is None
    assert (await session.get(type(planned.order), planned.order.id)).status == OrderStatus.COMPLETED
