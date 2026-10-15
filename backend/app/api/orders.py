import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.converters import audit_out, components_out, marking_out, order_row
from app.deps import ActorDep, SessionDep
from app.models import MarkingAttempt, MarkingReport, ProductionOrder
from app.schemas import CompleteIn, OrderCard, OrderIn, OrderRow, PlanPreviewRow, ReservationOut
from app.services import audit, orders, reports
from app.services.permissions import Perm, require

router = APIRouter(prefix="/api/orders", tags=["orders"])
log = logging.getLogger(__name__)


async def build_card(session, order_id: int) -> OrderCard:
    order = await orders.load_order(session, order_id)
    res = await orders.order_reservations(session, order.id)
    cons = await orders.order_consumptions(session, order.id)
    history = await audit.entries_for(session, "order", order.id)
    report = await session.scalar(select(MarkingReport).where(MarkingReport.order_id == order.id))
    attempts = (
        list(
            await session.scalars(
                select(MarkingAttempt)
                .where(MarkingAttempt.report_id == report.id)
                .order_by(MarkingAttempt.attempt_no)
            )
        )
        if report
        else []
    )
    row = order_row(order)
    return OrderCard(
        **row.model_dump(),
        comment=order.comment,
        created_at=order.created_at,
        started_at=order.started_at,
        completed_at=order.completed_at,
        components=components_out(order),
        reservations=[
            ReservationOut(
                batch_id=b.id,
                batch_number=b.number,
                material_id=r.material_id,
                qty=r.qty,
                received_date=b.received_date,
            )
            for r, b in res
        ],
        consumptions=[
            ReservationOut(
                batch_id=b.id,
                batch_number=b.number,
                material_id=c.material_id,
                qty=c.qty,
                received_date=b.received_date,
            )
            for c, b in cons
        ],
        history=[audit_out(h) for h in history],
        marking=marking_out(report, order.number, attempts, order) if report else None,
    )


@router.get("", response_model=list[OrderRow])
async def list_orders(
    session: SessionDep,
    actor: ActorDep,
    date_from: date | None = None,
    date_to: date | None = None,
    status: list[Literal["draft", "planned", "in_progress", "completed", "cancelled"]] | None = Query(None),
):
    rows = await orders.list_orders(session, actor, date_from=date_from, date_to=date_to, statuses=status)
    return [order_row(o) for o in rows]


@router.get("/preview", response_model=list[PlanPreviewRow])
async def preview(session: SessionDep, actor: ActorDep, recipe_id: int, qty: int = Query(gt=0, le=100_000)):
    return await orders.estimate_plan(session, actor, recipe_id=recipe_id, qty=qty)


@router.get("/shortages")
async def shortages(session: SessionDep, actor: ActorDep, date_from: date, date_to: date):
    return await reports.shortages_for_period(session, actor, date_from, date_to)


@router.post("", response_model=OrderCard)
async def create(body: OrderIn, session: SessionDep, actor: ActorDep):
    kwargs = dict(
        recipe_id=body.recipe_id,
        qty=body.qty,
        planned_date=body.planned_date,
        workshop=body.workshop,
        comment=body.comment,
    )
    if body.plan_now:
        result = await orders.create_and_plan(session, actor, **kwargs)
        order_id = result.order.id
    else:
        order = await orders.create_order(session, actor, **kwargs)
        await session.commit()
        order_id = order.id
    return await build_card(session, order_id)


@router.get("/{order_id}", response_model=OrderCard)
async def card(order_id: int, session: SessionDep, actor: ActorDep):
    require(actor, Perm.VIEW_STOCK)
    return await build_card(session, order_id)


@router.get("/{order_id}/cost")
async def cost(order_id: int, session: SessionDep, actor: ActorDep):
    number = await session.scalar(select(ProductionOrder.number).where(ProductionOrder.id == order_id))
    return await reports.order_cost(session, actor, number or "")


@router.post("/{order_id}/plan", response_model=OrderCard)
async def plan(order_id: int, session: SessionDep, actor: ActorDep):
    await orders.plan_order(session, actor, order_id)
    return await build_card(session, order_id)


@router.post("/{order_id}/start", response_model=OrderCard)
async def start(order_id: int, session: SessionDep, actor: ActorDep):
    await orders.start_order(session, actor, order_id)
    return await build_card(session, order_id)


@router.post("/{order_id}/cancel", response_model=OrderCard)
async def cancel(order_id: int, session: SessionDep, actor: ActorDep):
    await orders.cancel_order(session, actor, order_id)
    return await build_card(session, order_id)


@router.post("/{order_id}/complete", response_model=OrderCard)
async def complete(order_id: int, body: CompleteIn, request: Request, session: SessionDep, actor: ActorDep):
    await orders.complete_order(session, actor, order_id, body.actual)
    report_id = await session.scalar(select(MarkingReport.id).where(MarkingReport.order_id == order_id))
    # Не ждём сервис маркировки: ставим задачу в очередь и сразу отвечаем.
    # Если Redis недоступен — отчёт всё равно лежит в outbox, его подберёт периодическая задача.
    pool = getattr(request.app.state, "arq", None)
    if pool is not None and report_id is not None:
        try:
            await pool.enqueue_job("send_marking_report", report_id)
        except Exception:  # noqa: BLE001
            log.warning("Не удалось поставить отчёт %s в очередь, его подберёт cron", report_id)
    return await build_card(session, order_id)
