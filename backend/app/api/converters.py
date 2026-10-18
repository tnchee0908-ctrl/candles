"""ORM → схемы ответа API."""

from app.models import (
    BATCH_STATUS_TITLES,
    ORDER_STATUS_TITLES,
    AuditLog,
    Batch,
    BatchStatus,
    MarkingReport,
    Material,
    OrderStatus,
    ProductionOrder,
    Supplier,
)
from app.schemas import AuditOut, BatchRow, ComponentOut, MarkingOut, OrderRow
from app.services.batches import free_qty
from app.services.common import fmt_num
from app.services.orders import traffic_light


def batch_row(b: Batch, m: Material, s: Supplier) -> BatchRow:
    return BatchRow(
        id=b.id,
        number=b.number,
        received_date=b.received_date,
        material_code=m.code,
        material=m.name,
        unit=m.unit,
        supplier=s.name,
        qty=b.qty,
        remaining_qty=b.remaining_qty,
        reserved_qty=b.reserved_qty,
        free_qty=free_qty(b),
        price=b.price,
        currency=b.currency,
        rate=b.rate,
        rate_date=b.rate_date,
        unit_cost_rub=b.unit_cost_rub,
        status=b.status,
        status_title=BATCH_STATUS_TITLES[BatchStatus(b.status)],
        comment=b.comment,
    )


def audit_out(a: AuditLog) -> AuditOut:
    return AuditOut.model_validate(a, from_attributes=True)


def components_out(o: ProductionOrder) -> list[ComponentOut]:
    return [
        ComponentOut(
            material_id=c.material_id,
            material_code=c.material.code,
            material=c.material.name,
            unit=c.material.unit,
            required_qty=c.required_qty,
            reserved_qty=c.reserved_qty,
            missing_qty=max(c.required_qty - c.reserved_qty, 0)
            if o.status in (OrderStatus.DRAFT, OrderStatus.PLANNED)
            else 0,
            actual_qty=c.actual_qty,
            light=traffic_light(c, o.status),  # type: ignore[arg-type]
        )
        for c in o.components
    ]


def order_light(o: ProductionOrder) -> str:
    lights = {traffic_light(c, o.status) for c in o.components}
    if lights == {"green"}:
        return "green"
    if lights == {"red"}:
        return "red"
    return "yellow"


def order_row(o: ProductionOrder) -> OrderRow:
    return OrderRow(
        id=o.id,
        number=o.number,
        product=o.recipe.name,
        recipe_id=o.recipe_id,
        qty=o.qty,
        planned_date=o.planned_date,
        workshop=o.workshop,
        status=o.status,
        status_title=ORDER_STATUS_TITLES[OrderStatus(o.status)],
        light=order_light(o),  # type: ignore[arg-type]
        deficit_summary=deficit_summary(o),
    )


def deficit_summary(o: ProductionOrder) -> str | None:
    if o.status not in (OrderStatus.DRAFT, OrderStatus.PLANNED):
        return None
    missing = [c for c in o.components if c.reserved_qty < c.required_qty]
    if not missing or o.status == OrderStatus.DRAFT:
        return None
    first = missing[0]
    text = f"{fmt_num(first.required_qty - first.reserved_qty)} {first.material.unit} «{first.material.name}»"
    return text + (f" и ещё {len(missing) - 1}" if len(missing) > 1 else "")


def marking_out(
    r: MarkingReport, order_number: str | None = None, attempts=None, order: ProductionOrder | None = None
) -> MarkingOut:
    return MarkingOut(
        id=r.id,
        order_id=r.order_id,
        order_number=order_number,
        product=order.recipe.name if order else None,
        qty=order.qty if order else None,
        completed_at=order.completed_at if order else None,
        status=r.status,
        attempts=r.attempts,
        next_attempt_at=r.next_attempt_at if r.status == "pending" else None,
        last_error=r.last_error,
        external_id=r.external_id,
        sent_at=r.sent_at,
        idempotency_key=r.idempotency_key,
        attempt_log=[
            {
                "attempt_no": a.attempt_no,
                "at": a.at,
                "status_code": a.status_code,
                "error": a.error,
                "duration_ms": a.duration_ms,
            }
            for a in (attempts or [])
        ],
    )
