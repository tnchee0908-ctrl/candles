"""Аналитические функции поверх учётных данных. Их вызывают и экраны, и инструменты ассистента."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import DomainError
from app.models import (
    ORDER_STATUS_TITLES,
    Batch,
    BatchStatus,
    Consumption,
    Material,
    OrderStatus,
)
from app.services import orders as orders_service
from app.services.common import Actor, q_money
from app.services.permissions import Perm, has_perm, require

MAX_PERIOD_DAYS = 400


def _check_period(date_from: date, date_to: date) -> None:
    if date_from > date_to:
        raise DomainError("Начало периода позже конца.")
    if (date_to - date_from).days > MAX_PERIOD_DAYS:
        raise DomainError(f"Период не может быть длиннее {MAX_PERIOD_DAYS} дней.")


async def find_materials(session: AsyncSession, query: str) -> list[Material]:
    query = query.strip()
    if not query:
        raise DomainError("Укажите материал (код или часть названия).")
    exact = await session.scalar(select(Material).where(func.upper(Material.code) == query.upper()))
    if exact:
        return [exact]
    words = [w for w in query.lower().split() if len(w) >= 3] or [query.lower()]
    stmt = select(Material)
    for w in words:
        # Ищем по основе слова, чтобы «воска»/«воск» находили «Воск соевый».
        stem = w[:-1] if len(w) > 4 else w
        escaped = stem.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(
            or_(Material.name.ilike(f"%{escaped}%", escape="\\"), Material.code.ilike(f"%{escaped}%"))
        )
    return list(await session.scalars(stmt.order_by(Material.code).limit(20)))


async def material_stock(
    session: AsyncSession, actor: Actor, query: str | None = None
) -> list[dict[str, Any]]:
    """Остаток (принятые партии), резерв, свободный остаток, плюс сколько ждёт приёмки."""
    require(actor, Perm.VIEW_STOCK)
    materials = (
        await find_materials(session, query)
        if query
        else list(await session.scalars(select(Material).order_by(Material.code)))
    )
    if not materials:
        return []
    ids = [m.id for m in materials]
    accepted = Batch.status == BatchStatus.ACCEPTED
    stmt = (
        select(
            Batch.material_id,
            func.coalesce(func.sum(case((accepted, Batch.remaining_qty), else_=0)), 0),
            func.coalesce(func.sum(case((accepted, Batch.reserved_qty), else_=0)), 0),
            func.coalesce(
                func.sum(case((Batch.status == BatchStatus.ON_CHECK, Batch.remaining_qty), else_=0)), 0
            ),
            func.count(case((accepted & (Batch.remaining_qty > 0), 1))),
        )
        .where(Batch.material_id.in_(ids))
        .group_by(Batch.material_id)
    )
    agg = {row[0]: row[1:] for row in (await session.execute(stmt)).all()}
    result = []
    for m in materials:
        on_hand, reserved, on_check, batches = agg.get(m.id, (0, 0, 0, 0))
        on_hand, reserved, on_check = Decimal(on_hand), Decimal(reserved), Decimal(on_check)
        result.append(
            {
                "material_code": m.code,
                "material": m.name,
                "unit": m.unit,
                "on_hand": on_hand,
                "reserved": reserved,
                "free": on_hand - reserved,
                "awaiting_inspection": on_check,
                "batches_with_stock": int(batches),
            }
        )
    return result


async def shortages_for_period(
    session: AsyncSession, actor: Actor, date_from: date, date_to: date, workshop: int | None = None
) -> dict[str, Any]:
    """Дефицит по незапущенным заданиям периода.

    Непокрытая потребность = требуется − уже зарезервировано. Её сравниваем со свободным остатком
    сейчас: если свободного не хватает — это реальный дефицит, который нужно закупить.
    """
    require(actor, Perm.VIEW_STOCK)
    _check_period(date_from, date_to)
    orders = await orders_service.list_orders(
        session,
        actor,
        date_from=date_from,
        date_to=date_to,
        statuses=[OrderStatus.DRAFT, OrderStatus.PLANNED],
        workshop=workshop,
    )
    need: dict[int, Decimal] = defaultdict(Decimal)
    materials: dict[int, Material] = {}
    per_order = []
    for o in orders:
        missing = []
        for c in o.components:
            gap = c.required_qty - c.reserved_qty
            if gap > 0:
                need[c.material_id] += gap
                materials[c.material_id] = c.material
                missing.append(
                    {
                        "material_code": c.material.code,
                        "material": c.material.name,
                        "unit": c.material.unit,
                        "not_reserved": gap,
                    }
                )
        per_order.append(
            {
                "order_number": o.number,
                "product": o.recipe.name,
                "qty": o.qty,
                "planned_date": o.planned_date,
                "workshop": o.workshop,
                "status": ORDER_STATUS_TITLES[OrderStatus(o.status)],
                "not_reserved": missing,
            }
        )
    free = await orders_service.free_stock_by_material(session, list(need))
    stock = {s["material_code"]: s for s in await material_stock(session, actor)} if need else {}
    by_material = []
    for mid, gap in sorted(need.items(), key=lambda kv: materials[kv[0]].code):
        m = materials[mid]
        available = free.get(mid, Decimal(0))
        by_material.append(
            {
                "material_code": m.code,
                "material": m.name,
                "unit": m.unit,
                "not_reserved_need": gap,
                "free_stock_now": available,
                "awaiting_inspection": stock.get(m.code, {}).get("awaiting_inspection", Decimal(0)),
                "shortage": max(gap - available, Decimal(0)),
            }
        )
    return {
        "period": {"from": date_from, "to": date_to},
        "orders_considered": len(orders),
        "orders": per_order,
        "by_material": by_material,
        "materials_short": [r for r in by_material if r["shortage"] > 0],
    }


async def order_cost(session: AsyncSession, actor: Actor, order_number: str) -> dict[str, Any]:
    """Себестоимость: для завершённых — по фактическим списаниям; иначе — оценка по резервам."""
    require(actor, Perm.VIEW_COSTS)
    order_id = await orders_service.find_order_id(session, order_number)
    order = await orders_service.load_order(session, order_id)
    lines = []
    total = Decimal(0)
    unpriced = []
    if order.status == OrderStatus.COMPLETED:
        basis = "фактическое списание"
        rows = await orders_service.order_consumptions(session, order.id)
        by_mat: dict[int, list] = defaultdict(list)
        for cons, batch in rows:
            by_mat[cons.material_id].append((cons.qty, cons.unit_cost_rub, batch.number))
    else:
        basis = "оценка по текущему резерву"
        rows2 = await orders_service.order_reservations(session, order.id)
        by_mat = defaultdict(list)
        for res, batch in rows2:
            by_mat[res.material_id].append((res.qty, batch.unit_cost_rub, batch.number))
    for c in order.components:
        parts = by_mat.get(c.material_id, [])
        qty = sum((p[0] for p in parts), Decimal(0))
        cost = sum((p[0] * p[1] for p in parts), Decimal(0))
        total += cost
        if order.status != OrderStatus.COMPLETED and qty < c.required_qty:
            unpriced.append(
                {
                    "material": c.material.name,
                    "unit": c.material.unit,
                    "qty_without_price": c.required_qty - qty,
                }
            )
        lines.append(
            {
                "material_code": c.material.code,
                "material": c.material.name,
                "unit": c.material.unit,
                "qty": qty,
                "cost_rub": q_money(cost),
                "batches": [p[2] for p in parts],
            }
        )
    return {
        "order_number": order.number,
        "product": order.recipe.name,
        "qty": order.qty,
        "status": ORDER_STATUS_TITLES[OrderStatus(order.status)],
        "basis": basis,
        "total_cost_rub": q_money(total),
        "cost_per_unit_rub": q_money(total / order.qty) if order.qty else None,
        "lines": lines,
        "not_priced_yet": unpriced,
        "complete": not unpriced,
    }


async def consumption_by_week(
    session: AsyncSession, actor: Actor, date_from: date, date_to: date, material_query: str | None = None
) -> list[dict[str, Any]]:
    """Фактический расход материалов по неделям (понедельник недели). Стоимость — только при праве на неё."""
    require(actor, Perm.VIEW_STOCK)
    _check_period(date_from, date_to)
    week = func.date_trunc("week", Consumption.consumed_at)
    stmt = (
        select(
            week,
            Material.code,
            Material.name,
            Material.unit,
            func.sum(Consumption.qty),
            func.sum(Consumption.qty * Consumption.unit_cost_rub),
        )
        .join(Material, Material.id == Consumption.material_id)
        .where(func.date(Consumption.consumed_at) >= date_from, func.date(Consumption.consumed_at) <= date_to)
        .group_by(week, Material.code, Material.name, Material.unit)
        .order_by(week, Material.code)
    )
    if material_query:
        mats = await find_materials(session, material_query)
        if not mats:
            return []
        stmt = stmt.where(Consumption.material_id.in_([m.id for m in mats]))
    show_cost = has_perm(actor, Perm.VIEW_COSTS)
    out = []
    for wk, code, name, unit, qty, cost in (await session.execute(stmt)).all():
        row = {
            "week_start": wk.date(),
            "material_code": code,
            "material": name,
            "unit": unit,
            "qty": Decimal(qty),
        }
        if show_cost:
            row["cost_rub"] = q_money(Decimal(cost))
        out.append(row)
    return out


def week_bounds(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)
