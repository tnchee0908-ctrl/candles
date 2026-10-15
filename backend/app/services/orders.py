"""Производственные задания: жизненный цикл, FIFO-резервирование, списание.

Черновик → Запланировано → В работе → Завершено; Черновик/Запланировано → Отменено.

Конкурентность: свободный остаток партии = remaining_qty − reserved_qty. Перед резервом строки партий
блокируются SELECT … FOR UPDATE, поэтому два параллельных запроса выстраиваются в очередь на уровне
PostgreSQL, и второй видит уже уменьшенный свободный остаток. Страховка — CHECK reserved_qty <= remaining_qty.
Блокировки берутся в одном порядке (материал по id, партии по FIFO), чтобы не было взаимоблокировок.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import Conflict, DomainError, NotFound
from app.models import (
    ORDER_STATUS_TITLES,
    Batch,
    BatchStatus,
    Consumption,
    MarkingReport,
    Material,
    OrderComponent,
    OrderStatus,
    ProductionOrder,
    Recipe,
    RecipeItem,
    Reservation,
)
from app.services import audit
from app.services.common import Actor, fmt_num, q_qty
from app.services.permissions import Perm, require

MAX_ORDER_QTY = 100_000


@dataclass
class Shortage:
    material_id: int
    material_code: str
    material_name: str
    unit: str
    required: Decimal
    reserved: Decimal

    @property
    def missing(self) -> Decimal:
        return self.required - self.reserved


@dataclass
class PlanResult:
    order: ProductionOrder
    shortages: list[Shortage] = field(default_factory=list)


def order_snapshot(o: ProductionOrder) -> dict[str, Any]:
    return {
        "status": o.status,
        "qty": o.qty,
        "planned_date": o.planned_date,
        "workshop": o.workshop,
        "components": {
            str(c.material_id): {
                "required": c.required_qty,
                "reserved": c.reserved_qty,
                "actual": c.actual_qty,
            }
            for c in o.components
        },
    }


async def load_order(session: AsyncSession, order_id: int, *, lock: bool = False) -> ProductionOrder:
    stmt = (
        select(ProductionOrder)
        .where(ProductionOrder.id == order_id)
        .options(
            selectinload(ProductionOrder.components).selectinload(OrderComponent.material),
            selectinload(ProductionOrder.recipe),
        )
        .execution_options(populate_existing=True)
    )
    if lock:
        # Блокируем только строку задания (of=...), чтобы два запроса не меняли одно задание одновременно.
        stmt = stmt.with_for_update(of=ProductionOrder)
    order = await session.scalar(stmt)
    if order is None:
        raise NotFound("Задание не найдено.")
    return order


async def find_order_id(session: AsyncSession, number: str) -> int:
    order_id = await session.scalar(
        select(ProductionOrder.id).where(ProductionOrder.number == number.strip().upper())
    )
    if order_id is None:
        raise NotFound(f"Задание {number} не найдено.")
    return order_id


def _audit(
    session: AsyncSession, actor: Actor, order: ProductionOrder, action: str, before: dict | None
) -> None:
    audit.record(
        session,
        actor,
        entity_type="order",
        entity_id=order.id,
        entity_label=order.number,
        action=action,
        before=before,
        after=order_snapshot(order),
    )


def _require_status(order: ProductionOrder, allowed: set[OrderStatus], action: str) -> None:
    if OrderStatus(order.status) not in allowed:
        raise Conflict(
            f"Задание {order.number} в статусе «{ORDER_STATUS_TITLES[OrderStatus(order.status)]}» — {action} нельзя."
        )


# ---------- Создание и планирование ----------


async def create_order(
    session: AsyncSession,
    actor: Actor,
    *,
    recipe_id: int,
    qty: int,
    planned_date: date,
    workshop: int = 1,
    comment: str | None = None,
) -> ProductionOrder:
    """Черновик задания: потребность = норма рецепта на 1 шт × количество."""
    require(actor, Perm.MANAGE_ORDERS)
    if not 0 < qty <= MAX_ORDER_QTY:
        raise DomainError(f"Количество должно быть от 1 до {fmt_num(MAX_ORDER_QTY)} шт.")
    if workshop not in (1, 2, 3):
        raise DomainError("Цех должен быть 1, 2 или 3.")
    if planned_date < date.today():
        raise DomainError("Дата задания не может быть в прошлом.")
    recipe = await session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.items).selectinload(RecipeItem.material))
    )
    if recipe is None:
        raise NotFound("Рецепт не найден.")
    if not recipe.items:
        raise DomainError(f"В рецепте «{recipe.name}» нет материалов.")

    order = ProductionOrder(
        recipe_id=recipe.id,
        qty=qty,
        planned_date=planned_date,
        workshop=workshop,
        status=OrderStatus.DRAFT.value,
        comment=comment,
        created_by_id=actor.user_id,
    )
    order.components = [
        OrderComponent(
            material_id=item.material_id,
            required_qty=q_qty(item.qty_per_unit * qty),
            reserved_qty=Decimal(0),
        )
        for item in sorted(recipe.items, key=lambda i: i.material_id)
    ]
    session.add(order)
    await session.flush()
    await session.refresh(order, ["number"])
    _audit(session, actor, order, "Задание создано", None)
    return order


async def _reserve_component(session: AsyncSession, order: ProductionOrder, comp: OrderComponent) -> None:
    """FIFO: сначала самые старые принятые партии. При нехватке — частичный резерв."""
    need = comp.required_qty - comp.reserved_qty
    if need <= 0:
        return
    batches = await session.scalars(
        select(Batch)
        .where(
            Batch.material_id == comp.material_id,
            Batch.status == BatchStatus.ACCEPTED,
            Batch.remaining_qty > 0,
        )
        .order_by(Batch.received_date, Batch.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    existing = {
        r.batch_id: r
        for r in await session.scalars(
            select(Reservation).where(
                Reservation.order_id == order.id, Reservation.material_id == comp.material_id
            )
        )
    }
    for batch in batches:
        free = batch.remaining_qty - batch.reserved_qty
        if free <= 0:
            continue
        take = min(free, need)
        batch.reserved_qty += take
        if batch.id in existing:
            existing[batch.id].qty += take
        else:
            session.add(
                Reservation(order_id=order.id, batch_id=batch.id, material_id=comp.material_id, qty=take)
            )
        comp.reserved_qty += take
        need -= take
        if need == 0:
            break


def shortages_of(order: ProductionOrder) -> list[Shortage]:
    return [
        Shortage(
            material_id=c.material_id,
            material_code=c.material.code,
            material_name=c.material.name,
            unit=c.material.unit,
            required=c.required_qty,
            reserved=c.reserved_qty,
        )
        for c in order.components
        if c.reserved_qty < c.required_qty
    ]


async def plan_order(
    session: AsyncSession, actor: Actor, order_id: int, *, commit: bool = True
) -> PlanResult:
    """Черновик → Запланировано с резервом. Повторный вызов для запланированного — дорезервировать дефицит."""
    require(actor, Perm.MANAGE_ORDERS)
    order = await load_order(session, order_id, lock=True)
    _require_status(order, {OrderStatus.DRAFT, OrderStatus.PLANNED}, "планировать")
    before = order_snapshot(order)
    was_draft = order.status == OrderStatus.DRAFT
    for comp in sorted(order.components, key=lambda c: c.material_id):
        await _reserve_component(session, order, comp)
    order.status = OrderStatus.PLANNED.value
    _audit(session, actor, order, "Задание запланировано" if was_draft else "Дорезервирование", before)
    await session.flush()
    if commit:
        await session.commit()
    return PlanResult(order=order, shortages=shortages_of(order))


async def create_and_plan(
    session: AsyncSession,
    actor: Actor,
    *,
    recipe_id: int,
    qty: int,
    planned_date: date,
    workshop: int = 1,
    comment: str | None = None,
) -> PlanResult:
    """Создать и сразу запланировать — одна транзакция. Этот же код вызывает кнопка и ассистент."""
    order = await create_order(
        session,
        actor,
        recipe_id=recipe_id,
        qty=qty,
        planned_date=planned_date,
        workshop=workshop,
        comment=comment,
    )
    result = await plan_order(session, actor, order.id, commit=False)
    await session.commit()
    return result


async def estimate_plan(
    session: AsyncSession, actor: Actor, *, recipe_id: int, qty: int
) -> list[dict[str, Any]]:
    """Что будет зарезервировано, если запланировать сейчас (без изменений в БД) — для предпросмотра."""
    require(actor, Perm.VIEW_STOCK)
    recipe = await session.scalar(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.items).selectinload(RecipeItem.material))
    )
    if recipe is None:
        raise NotFound("Рецепт не найден.")
    free = await free_stock_by_material(session, [i.material_id for i in recipe.items])
    rows = []
    for item in sorted(recipe.items, key=lambda i: i.material_id):
        required = q_qty(item.qty_per_unit * qty)
        available = free.get(item.material_id, Decimal(0))
        rows.append(
            {
                "material_code": item.material.code,
                "material": item.material.name,
                "unit": item.material.unit,
                "required": required,
                "free_now": available,
                "will_reserve": min(required, available),
                "shortage": max(required - available, Decimal(0)),
            }
        )
    return rows


async def free_stock_by_material(
    session: AsyncSession, material_ids: list[int] | None = None
) -> dict[int, Decimal]:
    stmt = (
        select(Batch.material_id, func.coalesce(func.sum(Batch.remaining_qty - Batch.reserved_qty), 0))
        .where(Batch.status == BatchStatus.ACCEPTED)
        .group_by(Batch.material_id)
    )
    if material_ids is not None:
        stmt = stmt.where(Batch.material_id.in_(material_ids))
    return {mid: Decimal(v) for mid, v in (await session.execute(stmt)).all()}


# ---------- Запуск, отмена ----------


async def start_order(session: AsyncSession, actor: Actor, order_id: int) -> ProductionOrder:
    require(actor, Perm.MANAGE_ORDERS)
    order = await load_order(session, order_id, lock=True)
    _require_status(order, {OrderStatus.PLANNED}, "запустить")
    missing = shortages_of(order)
    if missing:
        details = "; ".join(f"{fmt_num(s.missing)} {s.unit} «{s.material_name}»" for s in missing)
        raise Conflict(f"Нельзя запустить задание {order.number} с дефицитом. Не хватает: {details}.")
    before = order_snapshot(order)
    order.status = OrderStatus.IN_PROGRESS.value
    order.started_at = datetime.now(UTC)
    _audit(session, actor, order, "Задание запущено", before)
    await session.commit()
    return order


async def _release_reservations(session: AsyncSession, order: ProductionOrder) -> None:
    reservations = list(
        await session.scalars(
            select(Reservation)
            .where(Reservation.order_id == order.id)
            .join(Batch, Batch.id == Reservation.batch_id)
            .order_by(Reservation.material_id, Batch.received_date, Batch.id)
        )
    )
    for r in reservations:
        batch = await session.scalar(
            select(Batch)
            .where(Batch.id == r.batch_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        assert batch is not None
        batch.reserved_qty -= r.qty
        await session.delete(r)
    for c in order.components:
        c.reserved_qty = Decimal(0)


async def cancel_order(session: AsyncSession, actor: Actor, order_id: int) -> ProductionOrder:
    require(actor, Perm.MANAGE_ORDERS)
    order = await load_order(session, order_id, lock=True)
    _require_status(
        order, {OrderStatus.DRAFT, OrderStatus.PLANNED}, "отменить (отмена возможна только до запуска)"
    )
    before = order_snapshot(order)
    await _release_reservations(session, order)
    order.status = OrderStatus.CANCELLED.value
    _audit(session, actor, order, "Задание отменено, резерв снят", before)
    await session.commit()
    return order


# ---------- Завершение ----------


def marking_idempotency_key(order: ProductionOrder) -> str:
    """Ключ зависит только от задания: повторная отправка того же отчёта не создаст дубль в маркировке."""
    return hashlib.sha256(f"candles:order-completed:{order.id}".encode()).hexdigest()[:40]


async def complete_order(
    session: AsyncSession, actor: Actor, order_id: int, actual: dict[int, Decimal]
) -> ProductionOrder:
    """Завершение с фактическим расходом.

    Резерв списывается по FIFO в пределах факта; экономия (резерв − факт) остаётся в партиях;
    перерасход (факт − резерв) досписывается из свободного остатка по FIFO.
    Отчёт в маркировку кладётся в outbox в той же транзакции и отправляется фоном.
    """
    require(actor, Perm.MANAGE_ORDERS)
    order = await load_order(session, order_id, lock=True)
    _require_status(order, {OrderStatus.IN_PROGRESS}, "завершить")
    component_ids = {c.material_id for c in order.components}
    unknown = set(actual) - component_ids
    if unknown:
        raise DomainError("В фактическом расходе есть материалы, которых нет в задании.")
    missing_input = [c.material.name for c in order.components if c.material_id not in actual]
    if missing_input:
        raise DomainError(f"Укажите фактический расход: {', '.join(missing_input)}.")
    for qty in actual.values():
        if qty < 0:
            raise DomainError("Фактический расход не может быть отрицательным.")

    before = order_snapshot(order)
    for comp in sorted(order.components, key=lambda c: c.material_id):
        await _consume_component(session, order, comp, q_qty(actual[comp.material_id]))

    order.status = OrderStatus.COMPLETED.value
    order.completed_at = datetime.now(UTC)
    _audit(session, actor, order, "Задание завершено", before)

    session.add(
        MarkingReport(
            order_id=order.id,
            idempotency_key=marking_idempotency_key(order),
            payload={
                "order_number": order.number,
                "product": order.recipe.name,
                "qty": order.qty,
                "completed_at": order.completed_at.isoformat(),
                "workshop": order.workshop,
            },
        )
    )
    await session.commit()
    return order


async def _consume_component(
    session: AsyncSession, order: ProductionOrder, comp: OrderComponent, actual_qty: Decimal
) -> None:
    rows = (
        await session.execute(
            select(Reservation, Batch)
            .join(Batch, Batch.id == Reservation.batch_id)
            .where(Reservation.order_id == order.id, Reservation.material_id == comp.material_id)
            .order_by(Batch.received_date, Batch.id)
            .with_for_update(of=Batch)
            .execution_options(populate_existing=True)
        )
    ).all()
    to_consume = actual_qty
    for reservation, batch in rows:
        take = min(reservation.qty, to_consume)
        batch.reserved_qty -= reservation.qty  # снимаем весь резерв; неиспользованное возвращается в партию
        batch.remaining_qty -= take
        if take > 0:
            session.add(_consumption(order, batch, take))
        to_consume -= take
        await session.delete(reservation)

    if to_consume > 0:  # перерасход — досписываем из свободного остатка по FIFO
        batches = await session.scalars(
            select(Batch)
            .where(
                Batch.material_id == comp.material_id,
                Batch.status == BatchStatus.ACCEPTED,
                Batch.remaining_qty > 0,
            )
            .order_by(Batch.received_date, Batch.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        for batch in batches:
            free = batch.remaining_qty - batch.reserved_qty
            if free <= 0:
                continue
            take = min(free, to_consume)
            batch.remaining_qty -= take
            session.add(_consumption(order, batch, take))
            to_consume -= take
            if to_consume == 0:
                break
        if to_consume > 0:
            raise DomainError(
                f"Не хватает {fmt_num(to_consume)} {comp.material.unit} «{comp.material.name}», "
                "чтобы списать перерасход. Проверьте фактический расход или оформите поступление."
            )
    comp.actual_qty = actual_qty
    comp.reserved_qty = Decimal(0)


def _consumption(order: ProductionOrder, batch: Batch, qty: Decimal) -> Consumption:
    return Consumption(
        order_id=order.id,
        batch_id=batch.id,
        material_id=batch.material_id,
        qty=qty,
        unit_cost_rub=batch.unit_cost_rub,
    )


# ---------- Чтение ----------


async def list_orders(
    session: AsyncSession,
    actor: Actor,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    statuses: list[str] | None = None,
    workshop: int | None = None,
    limit: int = 200,
) -> list[ProductionOrder]:
    require(actor, Perm.VIEW_STOCK)
    stmt = select(ProductionOrder).options(
        selectinload(ProductionOrder.recipe),
        selectinload(ProductionOrder.components).selectinload(OrderComponent.material),
    )
    if date_from:
        stmt = stmt.where(ProductionOrder.planned_date >= date_from)
    if date_to:
        stmt = stmt.where(ProductionOrder.planned_date <= date_to)
    if statuses:
        stmt = stmt.where(ProductionOrder.status.in_(statuses))
    if workshop:
        stmt = stmt.where(ProductionOrder.workshop == workshop)
    rows = await session.scalars(stmt.order_by(ProductionOrder.planned_date, ProductionOrder.id).limit(limit))
    return list(rows)


def traffic_light(comp: OrderComponent, order_status: str) -> str:
    """Светофор компонента: green — всё в резерве, yellow — часть, red — ничего."""
    if order_status in (OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED):
        return "green"
    if comp.reserved_qty >= comp.required_qty:
        return "green"
    if comp.reserved_qty > 0:
        return "yellow"
    return "red"


async def order_reservations(session: AsyncSession, order_id: int) -> list[tuple[Reservation, Batch]]:
    rows = await session.execute(
        select(Reservation, Batch)
        .join(Batch, Batch.id == Reservation.batch_id)
        .where(Reservation.order_id == order_id)
        .order_by(Reservation.material_id, Batch.received_date, Batch.id)
    )
    return [tuple(r) for r in rows.all()]  # type: ignore[misc]


async def order_consumptions(session: AsyncSession, order_id: int) -> list[tuple[Consumption, Batch]]:
    rows = await session.execute(
        select(Consumption, Batch)
        .join(Batch, Batch.id == Consumption.batch_id)
        .where(Consumption.order_id == order_id)
        .order_by(Consumption.material_id, Consumption.id)
    )
    return [tuple(r) for r in rows.all()]  # type: ignore[misc]


async def get_material(session: AsyncSession, material_id: int) -> Material:
    m = await session.get(Material, material_id)
    if m is None:
        raise NotFound("Материал не найден.")
    return m
