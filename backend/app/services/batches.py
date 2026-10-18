from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import DomainError, NotFound
from app.models import (
    BATCH_STATUS_TITLES,
    Batch,
    BatchStatus,
    Consumption,
    Material,
    ProductionOrder,
    Receipt,
    Reservation,
    Supplier,
)
from app.services import audit
from app.services.common import Actor, q_money, q_qty, today
from app.services.names import supplier_core
from app.services.permissions import Perm, require
from app.services.rates import RatesClient, get_rate

MAX_RECEIPT_AGE_DAYS = 5 * 366


@dataclass
class ReceiptLine:
    material_code: str
    qty: Decimal
    price: Decimal
    currency: str
    comment: str | None = None


def free_qty(b: Batch) -> Decimal:
    """Свободный остаток есть только у принятой партии: брак и непроверенное взять нельзя."""
    return b.remaining_qty - b.reserved_qty if b.status == BatchStatus.ACCEPTED else Decimal(0)


def batch_snapshot(b: Batch) -> dict[str, Any]:
    return {
        "status": b.status,
        "qty": b.qty,
        "remaining_qty": b.remaining_qty,
        "reserved_qty": b.reserved_qty,
        "comment": b.comment,
    }


async def get_or_create_supplier(session: AsyncSession, name: str) -> Supplier:
    name = " ".join(name.split())
    if not name:
        raise DomainError("Укажите поставщика.")
    # Ищем по нормализованному названию, чтобы «Восковой двор, ООО» не стал вторым поставщиком.
    key = supplier_core(name)
    supplier = next(
        (
            s
            for s in await session.scalars(select(Supplier))
            if key in {supplier_core(v) for v in [s.name, *(s.aliases or [])]}
        ),
        None,
    )
    if supplier is None:
        supplier = Supplier(name=name, aliases=[])
        session.add(supplier)
        await session.flush()
    return supplier


async def create_receipt(
    session: AsyncSession,
    actor: Actor,
    *,
    supplier_name: str,
    received_date: date,
    lines: list[ReceiptLine],
    rates_client: RatesClient | None = None,
) -> Receipt:
    """Поступление: каждая строка становится партией «На проверке» с себестоимостью в рублях."""
    require(actor, Perm.CREATE_RECEIPT)
    if not lines:
        raise DomainError("В поступлении нет ни одной строки.")
    if received_date > today():
        raise DomainError("Дата поступления не может быть в будущем.")
    if received_date < today() - timedelta(days=MAX_RECEIPT_AGE_DAYS):
        raise DomainError("Дата поступления слишком давняя: оформить можно поставку не старше 5 лет.")

    supplier = await get_or_create_supplier(session, supplier_name)
    receipt = Receipt(supplier_id=supplier.id, received_date=received_date, created_by_id=actor.user_id)
    session.add(receipt)
    await session.flush()

    for i, line in enumerate(lines, start=1):
        material = await session.scalar(select(Material).where(Material.code == line.material_code))
        if material is None:
            raise DomainError(f"Строка {i}: материал с кодом «{line.material_code}» не найден.")
        if line.qty <= 0:
            raise DomainError(f"Строка {i}: количество должно быть больше нуля.")
        if line.price < 0:
            raise DomainError(f"Строка {i}: цена не может быть отрицательной.")
        rate, rate_date = await get_rate(session, line.currency, received_date, rates_client)
        batch = Batch(
            receipt_id=receipt.id,
            material_id=material.id,
            received_date=received_date,
            qty=q_qty(line.qty),
            remaining_qty=q_qty(line.qty),
            reserved_qty=Decimal(0),
            price=q_money(line.price),
            currency=line.currency,
            rate=rate,
            rate_date=rate_date,
            unit_cost_rub=(line.price * rate).quantize(Decimal("0.000001")),
            status=BatchStatus.ON_CHECK.value,
            comment=line.comment,
        )
        session.add(batch)
        await session.flush()
        await session.refresh(batch, ["number"])
        audit.record(
            session,
            actor,
            entity_type="batch",
            entity_id=batch.id,
            entity_label=batch.number,
            action="Партия создана",
            before=None,
            after=batch_snapshot(batch)
            | {
                "material": material.code,
                "price": batch.price,
                "currency": batch.currency,
                "rate": batch.rate,
                "rate_date": batch.rate_date,
                "unit_cost_rub": batch.unit_cost_rub,
            },
        )

    await session.refresh(receipt, ["number"])
    await session.commit()
    return receipt


ALLOWED_TRANSITIONS = {
    BatchStatus.ON_CHECK: {BatchStatus.ACCEPTED, BatchStatus.REJECTED},
}


async def set_status(session: AsyncSession, actor: Actor, batch_id: int, status: str) -> Batch:
    require(actor, Perm.SET_BATCH_STATUS)
    batch = await session.scalar(
        select(Batch).where(Batch.id == batch_id).with_for_update().execution_options(populate_existing=True)
    )
    if batch is None:
        raise NotFound("Партия не найдена.")
    try:
        new_status = BatchStatus(status)
    except ValueError as exc:
        raise DomainError(f"Неизвестный статус партии: {status}") from exc
    current = BatchStatus(batch.status)
    if new_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise DomainError(
            f"Партию {batch.number} нельзя перевести из «{BATCH_STATUS_TITLES[current]}» "
            f"в «{BATCH_STATUS_TITLES[new_status]}»."
        )
    before = batch_snapshot(batch)
    batch.status = new_status.value
    audit.record(
        session,
        actor,
        entity_type="batch",
        entity_id=batch.id,
        entity_label=batch.number,
        action=f"Статус: {BATCH_STATUS_TITLES[new_status]}",
        before=before,
        after=batch_snapshot(batch),
    )
    await session.commit()
    return batch


# ---------- Реестр партий ----------

SORTABLE = {
    "number": Batch.id,
    "received_date": Batch.received_date,
    "material": Material.name,
    "supplier": Supplier.name,
    "qty": Batch.qty,
    "remaining_qty": Batch.remaining_qty,
    "reserved_qty": Batch.reserved_qty,
    "free_qty": case(
        (Batch.status == BatchStatus.ACCEPTED, Batch.remaining_qty - Batch.reserved_qty), else_=0
    ),
    # Цены в разных валютах сравниваем в рублях, иначе 50 USD оказалось бы «дешевле» 60 RUB.
    "price": Batch.price * Batch.rate,
    "currency": Batch.currency,
    "unit_cost_rub": Batch.unit_cost_rub,
    "status": Batch.status,
}


@dataclass
class BatchFilters:
    number: str | None = None
    material: str | None = None
    supplier: str | None = None
    status: str | None = None
    currency: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    only_free: bool = False


def _registry_query(f: BatchFilters) -> Select:
    stmt = (
        select(Batch, Material, Supplier)
        .join(Material, Material.id == Batch.material_id)
        .join(Receipt, Receipt.id == Batch.receipt_id)
        .join(Supplier, Supplier.id == Receipt.supplier_id)
    )
    if f.number:
        stmt = stmt.where(Batch.number.ilike(f"%{_escape_like(f.number)}%", escape="\\"))
    if f.material:
        pattern = f"%{_escape_like(f.material)}%"
        stmt = stmt.where(
            or_(Material.name.ilike(pattern, escape="\\"), Material.code.ilike(pattern, escape="\\"))
        )
    if f.supplier:
        stmt = stmt.where(Supplier.name.ilike(f"%{_escape_like(f.supplier)}%", escape="\\"))
    if f.status:
        stmt = stmt.where(Batch.status == f.status)
    if f.currency:
        stmt = stmt.where(Batch.currency == f.currency)
    if f.date_from:
        stmt = stmt.where(Batch.received_date >= f.date_from)
    if f.date_to:
        stmt = stmt.where(Batch.received_date <= f.date_to)
    if f.only_free:
        stmt = stmt.where(Batch.status == BatchStatus.ACCEPTED, Batch.remaining_qty > Batch.reserved_qty)
    return stmt


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_batches(
    session: AsyncSession,
    actor: Actor,
    filters: BatchFilters,
    *,
    sort: str = "received_date",
    direction: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[tuple[Batch, Material, Supplier]], int]:
    require(actor, Perm.VIEW_STOCK)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    column = SORTABLE.get(sort)
    if column is None:
        raise DomainError(f"Нельзя сортировать по полю «{sort}».")
    stmt = _registry_query(filters)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    order = column.desc() if direction == "desc" else column.asc()
    rows = await session.execute(
        stmt.order_by(order, Batch.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return [tuple(r) for r in rows.all()], int(total or 0)  # type: ignore[misc]


async def get_batch_card(
    session: AsyncSession, actor: Actor, *, batch_id: int | None = None, number: str | None = None
):
    """Карточка и история партии: поступление, приёмка, резервы, списания."""
    require(actor, Perm.VIEW_STOCK)
    stmt = select(Batch).options(
        selectinload(Batch.material), selectinload(Batch.receipt).selectinload(Receipt.supplier)
    )
    if batch_id is not None:
        stmt = stmt.where(Batch.id == batch_id)
    elif number:
        stmt = stmt.where(func.upper(Batch.number) == number.strip().upper())
    else:
        raise DomainError("Укажите номер партии.")
    batch = await session.scalar(stmt)
    if batch is None:
        raise NotFound(f"Партия {number or batch_id} не найдена.")

    reservations = (
        await session.execute(
            select(Reservation, ProductionOrder)
            .join(ProductionOrder, ProductionOrder.id == Reservation.order_id)
            .where(Reservation.batch_id == batch.id)
            .order_by(Reservation.id)
        )
    ).all()
    consumptions = (
        await session.execute(
            select(Consumption, ProductionOrder)
            .join(ProductionOrder, ProductionOrder.id == Consumption.order_id)
            .where(Consumption.batch_id == batch.id)
            .order_by(Consumption.consumed_at, Consumption.id)
        )
    ).all()
    history = await audit.entries_for(session, "batch", batch.id)
    return batch, reservations, consumptions, history
