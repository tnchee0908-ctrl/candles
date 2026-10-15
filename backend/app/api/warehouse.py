from datetime import date
from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.converters import audit_out, batch_row, marking_out
from app.deps import ActorDep, SessionDep
from app.errors import NotFound
from app.models import Batch, MarkingAttempt, MarkingReport, ProductionOrder, Supplier
from app.schemas import (
    AuditPage,
    BatchCard,
    BatchPage,
    BatchRef,
    BatchStatusIn,
    MarkingOut,
    MaterialIn,
    MaterialOut,
    MovementOut,
    ReceiptIn,
    ReceiptOut,
    RecipeIn,
    RecipeItemOut,
    RecipeOut,
    StockOut,
)
from app.services import audit, batches, catalog, marking, reports
from app.services.batches import BatchFilters, ReceiptLine
from app.services.permissions import Perm, require

router = APIRouter(prefix="/api", tags=["warehouse"])


@router.get("/materials", response_model=list[MaterialOut])
async def list_materials(session: SessionDep, actor: ActorDep):
    return await catalog.list_materials(session, actor)


@router.post("/materials", response_model=MaterialOut)
async def create_material(body: MaterialIn, session: SessionDep, actor: ActorDep):
    return await catalog.create_material(session, actor, code=body.code, name=body.name, unit=body.unit)


@router.get("/stock", response_model=list[StockOut])
async def stock(session: SessionDep, actor: ActorDep, q: str | None = None):
    return await reports.material_stock(session, actor, q)


@router.get("/suppliers", response_model=list[str])
async def suppliers(session: SessionDep, actor: ActorDep):
    require(actor, Perm.VIEW_STOCK)
    return list(await session.scalars(select(Supplier.name).order_by(Supplier.name)))


def _recipe_out(r) -> RecipeOut:
    return RecipeOut(
        id=r.id,
        name=r.name,
        items=[
            RecipeItemOut(material=MaterialOut.model_validate(i.material), qty_per_unit=i.qty_per_unit)
            for i in r.items
        ],
    )


@router.get("/recipes", response_model=list[RecipeOut])
async def list_recipes(session: SessionDep, actor: ActorDep):
    return [_recipe_out(r) for r in await catalog.list_recipes(session, actor)]


@router.post("/recipes", response_model=RecipeOut)
async def create_recipe(body: RecipeIn, session: SessionDep, actor: ActorDep):
    recipe = await catalog.create_recipe(
        session, actor, name=body.name, items=[(i.material_code, i.qty_per_unit) for i in body.items]
    )
    full = next(r for r in await catalog.list_recipes(session, actor) if r.id == recipe.id)
    return _recipe_out(full)


@router.post("/receipts", response_model=ReceiptOut)
async def create_receipt(body: ReceiptIn, session: SessionDep, actor: ActorDep):
    receipt = await batches.create_receipt(
        session,
        actor,
        supplier_name=body.supplier,
        received_date=body.received_date,
        lines=[ReceiptLine(l.material_code, l.qty, l.price, l.currency, l.comment) for l in body.lines],  # noqa: E741
    )
    created = list(
        await session.scalars(select(Batch).where(Batch.receipt_id == receipt.id).order_by(Batch.id))
    )
    return ReceiptOut(
        id=receipt.id,
        number=receipt.number,
        batch_numbers=[b.number for b in created],
        batches=[BatchRef(id=b.id, number=b.number) for b in created],
    )


@router.get("/batches", response_model=BatchPage)
async def list_batches(
    session: SessionDep,
    actor: ActorDep,
    number: str | None = None,
    material: str | None = None,
    supplier: str | None = None,
    status: Literal["on_check", "accepted", "rejected"] | None = None,
    currency: Literal["RUB", "USD", "EUR"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    only_free: bool = False,
    sort: str = "received_date",
    direction: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    filters = BatchFilters(number, material, supplier, status, currency, date_from, date_to, only_free)
    rows, total = await batches.list_batches(
        session, actor, filters, sort=sort, direction=direction, page=page, page_size=page_size
    )
    return BatchPage(total=total, page=page, page_size=page_size, items=[batch_row(*r) for r in rows])


@router.get("/batches/{batch_id}", response_model=BatchCard)
async def batch_card(batch_id: int, session: SessionDep, actor: ActorDep):
    batch, reservations, consumptions, history = await batches.get_batch_card(
        session, actor, batch_id=batch_id
    )
    return BatchCard(
        batch=batch_row(batch, batch.material, batch.receipt.supplier),
        receipt_number=batch.receipt.number,
        reservations=[MovementOut(order_id=o.id, order_number=o.number, qty=r.qty) for r, o in reservations],
        consumptions=[
            MovementOut(order_id=o.id, order_number=o.number, qty=c.qty, at=c.consumed_at)
            for c, o in consumptions
        ],
        history=[audit_out(h) for h in history],
    )


@router.post("/batches/{batch_id}/status")
async def set_batch_status(batch_id: int, body: BatchStatusIn, session: SessionDep, actor: ActorDep):
    batch = await batches.set_status(session, actor, batch_id, body.status)
    return {"id": batch.id, "status": batch.status}


@router.get("/audit", response_model=AuditPage)
async def audit_log(
    session: SessionDep,
    actor: ActorDep,
    entity_type: str | None = None,
    entity_id: int | None = None,
    via_assistant: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    items, total = await audit.list_entries(
        session,
        actor,
        entity_type=entity_type,
        entity_id=entity_id,
        via_assistant=via_assistant,
        page=page,
        page_size=page_size,
    )
    return AuditPage(total=total, page=page, page_size=page_size, items=[audit_out(a) for a in items])


@router.get("/marking", response_model=list[MarkingOut])
async def marking_reports(session: SessionDep, actor: ActorDep):
    require(actor, Perm.VIEW_MARKING)
    rows = (
        await session.execute(
            select(MarkingReport, ProductionOrder)
            .join(ProductionOrder, ProductionOrder.id == MarkingReport.order_id)
            .options(selectinload(ProductionOrder.recipe))
            .order_by(MarkingReport.id.desc())
            .limit(100)
        )
    ).all()
    attempts: dict[int, list] = {}
    if rows:
        for a in await session.scalars(
            select(MarkingAttempt)
            .where(MarkingAttempt.report_id.in_([r.id for r, _ in rows]))
            .order_by(MarkingAttempt.attempt_no)
        ):
            attempts.setdefault(a.report_id, []).append(a)
    return [marking_out(r, o.number, attempts.get(r.id), o) for r, o in rows]


@router.post("/marking/{report_id}/retry", response_model=MarkingOut)
async def retry_marking(report_id: int, session: SessionDep, actor: ActorDep):
    require(actor, Perm.MANAGE_ORDERS)
    report = await marking.retry_report(session, report_id)
    if report is None:
        raise NotFound("Отчёт не найден.")
    return marking_out(report)
