"""Инструменты ассистента (function calling).

Каждый инструмент — тонкая обёртка над функцией сервисного слоя: те же проверки прав, те же правила,
что и у кнопок в интерфейсе. SQL модель не пишет. Аргументы от модели — внешний ввод: строгие
Pydantic-модели (extra="forbid", ограничения длины и диапазонов), ошибка валидации возвращается
модели текстом, а не роняет чат.
"""

import csv
import io
import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from string import Template
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import memory
from app.assistant.llm.base import ToolSpec
from app.assistant.pii import Pseudonymizer
from app.assistant.sandbox import Sandbox, SandboxError
from app.errors import DomainError, Forbidden
from app.models import (
    BATCH_STATUS_TITLES,
    ORDER_STATUS_TITLES,
    Batch,
    BatchStatus,
    OrderStatus,
    PendingAction,
)
from app.services import batches as batches_service
from app.services import catalog, orders, reports
from app.services.batches import BatchFilters
from app.services.common import Actor, fmt_num, q_money, today
from app.services.permissions import Perm, has_perm, require
from app.services.rates import get_rate

log = logging.getLogger(__name__)


@dataclass
class ToolContext:
    session: AsyncSession
    actor: Actor
    # Только id: после отката транзакции (ошибка в другом инструменте) ORM-объекты «протухают».
    conversation_id: int
    pii: Pseudonymizer
    assistant_message_id: int
    sandbox: Sandbox | None = None
    container_id: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    # Текст текущего сообщения пользователя: основание для фактов памяти проверяется по нему.
    user_message: str = ""


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Handler = Callable[[ToolContext, Any], Awaitable[dict[str, Any]]]


@dataclass
class Tool:
    name: str
    description: str
    params: dict[str, str]
    args_model: type[Args]
    handler: Handler
    kind: Literal["read", "action", "memory", "sandbox"] = "read"

    def spec(self) -> ToolSpec:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        for param, text in self.params.items():
            schema["properties"][param]["description"] = " ".join(text.split())
        return ToolSpec(name=self.name, description=self.description, parameters=schema)


REGISTRY: dict[str, Tool] = {}

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
# Тексты для модели (описания инструментов и аргументов, служебные пометки) лежат в prompts/*.yaml.
TEXTS: dict[str, dict[str, Any]] = yaml.safe_load((PROMPTS / "tools.yaml").read_text(encoding="utf-8"))
NOTES: dict[str, str] = yaml.safe_load((PROMPTS / "notes.yaml").read_text(encoding="utf-8"))


def tool(name: str, args_model: type[Args], kind: str = "read"):
    def deco(fn: Handler) -> Handler:
        text = TEXTS[name]
        REGISTRY[name] = Tool(
            name,
            text["description"],
            text.get("params") or {},
            args_model,
            fn,
            kind,  # type: ignore[arg-type]
        )
        return fn

    return deco


# ---------- Чтение ----------


class StockArgs(Args):
    material: str | None = Field(default=None, max_length=100)


@tool("get_material_stock", StockArgs)
async def get_material_stock(ctx: ToolContext, args: StockArgs) -> dict[str, Any]:
    rows = await reports.material_stock(ctx.session, ctx.actor, args.material)
    if not rows:
        return {"found": False, "message": f"Материал «{args.material}» не найден."}
    return {"found": True, "materials": rows}


class PeriodArgs(Args):
    date_from: date
    date_to: date
    workshop: int | None = Field(default=None, ge=1, le=3)


@tool("get_shortages", PeriodArgs)
async def get_shortages(ctx: ToolContext, args: PeriodArgs) -> dict[str, Any]:
    return await reports.shortages_for_period(
        ctx.session, ctx.actor, args.date_from, args.date_to, args.workshop
    )


class BatchArgs(Args):
    batch_number: str = Field(max_length=20)


def _normalize_number(value: str, prefix: str) -> str:
    v = value.strip().upper().replace(" ", "")
    digits = re.sub(r"\D", "", v)
    if not digits:
        raise DomainError(f"Некорректный номер: {value}")
    return f"{prefix}-{int(digits):05d}"


@tool("get_batch_history", BatchArgs)
async def get_batch_history(ctx: ToolContext, args: BatchArgs) -> dict[str, Any]:
    number = _normalize_number(args.batch_number, "П")
    batch, reservations, consumptions, history = await batches_service.get_batch_card(
        ctx.session, ctx.actor, number=number
    )
    show_cost = has_perm(ctx.actor, Perm.VIEW_COSTS) or has_perm(ctx.actor, Perm.CREATE_RECEIPT)
    data: dict[str, Any] = {
        "batch_number": batch.number,
        "material": f"{batch.material.name} ({batch.material.code})",
        "unit": batch.material.unit,
        "supplier": batch.receipt.supplier.name,
        "receipt_number": batch.receipt.number,
        "received_date": batch.received_date,
        "status": BATCH_STATUS_TITLES[BatchStatus(batch.status)],
        "qty_received": batch.qty,
        "remaining": batch.remaining_qty,
        "reserved": batch.reserved_qty,
        "free": batch.remaining_qty - batch.reserved_qty,
        # Комментарий — пользовательский текст. Помечаем явно, что это данные, а не инструкции.
        "comment_untrusted_data": batch.comment,
        "reservations": [{"order": o.number, "qty": r.qty} for r, o in reservations],
        "consumptions": [{"order": o.number, "qty": c.qty, "at": c.consumed_at} for c, o in consumptions],
        "history": [
            {"at": h.at, "who": h.user_full_name, "action": h.action, "via_assistant": h.via_assistant}
            for h in history
        ],
    }
    if show_cost:
        data |= {
            "price": batch.price,
            "currency": batch.currency,
            "rate": batch.rate,
            "rate_date": batch.rate_date,
            "unit_cost_rub": batch.unit_cost_rub,
        }
    return data


class OrderNumberArgs(Args):
    order_number: str = Field(max_length=20)


@tool("get_order_cost", OrderNumberArgs)
async def get_order_cost(ctx: ToolContext, args: OrderNumberArgs) -> dict[str, Any]:
    return await reports.order_cost(ctx.session, ctx.actor, _normalize_number(args.order_number, "З"))


OrderStatusLit = Literal["draft", "planned", "in_progress", "completed", "cancelled"]


class ListOrdersArgs(Args):
    date_from: date | None = Field(default=None)
    date_to: date | None = Field(default=None)
    statuses: list[OrderStatusLit] | None = Field(default=None, max_length=5)
    workshop: int | None = Field(default=None, ge=1, le=3)


@tool("list_orders", ListOrdersArgs)
async def list_orders(ctx: ToolContext, args: ListOrdersArgs) -> dict[str, Any]:
    rows = await orders.list_orders(
        ctx.session,
        ctx.actor,
        date_from=args.date_from,
        date_to=args.date_to,
        statuses=list(args.statuses) if args.statuses else None,
        workshop=args.workshop,
        limit=100,
    )
    return {
        "count": len(rows),
        "orders": [
            {
                "number": o.number,
                "product": o.recipe.name,
                "qty": o.qty,
                "planned_date": o.planned_date,
                "workshop": o.workshop,
                "status": ORDER_STATUS_TITLES[OrderStatus(o.status)],
                "fully_reserved": all(c.reserved_qty >= c.required_qty for c in o.components),
            }
            for o in rows
        ],
    }


class NoArgs(Args):
    pass


@tool("list_recipes", NoArgs)
async def list_recipes(ctx: ToolContext, args: NoArgs) -> dict[str, Any]:
    recipes = await catalog.list_recipes(ctx.session, ctx.actor)
    return {
        "recipes": [
            {
                "name": r.name,
                "norms_per_unit": [
                    {
                        "material": i.material.name,
                        "code": i.material.code,
                        "qty": i.qty_per_unit,
                        "unit": i.material.unit,
                    }
                    for i in r.items
                ],
            }
            for r in recipes
        ]
    }


class FindBatchesArgs(Args):
    material: str | None = Field(default=None, max_length=100)
    supplier: str | None = Field(default=None, max_length=100)
    status: Literal["on_check", "accepted", "rejected"] | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=20, ge=1, le=50)


@tool("find_batches", FindBatchesArgs)
async def find_batches(ctx: ToolContext, args: FindBatchesArgs) -> dict[str, Any]:
    rows, total = await batches_service.list_batches(
        ctx.session,
        ctx.actor,
        BatchFilters(
            material=args.material,
            supplier=args.supplier,
            status=args.status,
            date_from=args.date_from,
            date_to=args.date_to,
        ),
        page_size=args.limit,
    )
    return {
        "total": total,
        "shown": len(rows),
        "batches": [
            {
                "number": b.number,
                "material": m.name,
                "unit": m.unit,
                "supplier": s.name,
                "received_date": b.received_date,
                "status": BATCH_STATUS_TITLES[BatchStatus(b.status)],
                "remaining": b.remaining_qty,
                "free": b.remaining_qty - b.reserved_qty,
            }
            for b, m, s in rows
        ],
    }


class RateArgs(Args):
    currency: Literal["USD", "EUR"]
    on_date: date | None = Field(default=None)
    amounts_rub: list[Decimal] = Field(
        default_factory=list,
        max_length=50,
    )


@tool("get_currency_rate", RateArgs)
async def get_currency_rate(ctx: ToolContext, args: RateArgs) -> dict[str, Any]:
    on_date = args.on_date or today()
    rate, rate_date = await get_rate(ctx.session, args.currency, on_date)
    await ctx.session.commit()
    result: dict[str, Any] = {
        "currency": args.currency,
        "rub_per_unit": rate,
        "rate_date": rate_date,
        "requested_date": on_date,
    }
    if args.amounts_rub:
        # Пересчёт в Decimal с округлением до копеек (центов) — модель не считает деньги в уме.
        result["converted"] = [{"rub": a, args.currency.lower(): q_money(a / rate)} for a in args.amounts_rub]
    return result


# ---------- Действие ----------


class ProposeOrderArgs(Args):
    recipe: str = Field(max_length=100)
    qty: int = Field(ge=1, le=100_000)
    planned_date: date
    workshop: int = Field(default=1, ge=1, le=3)
    comment: str | None = Field(default=None, max_length=300)


@tool("propose_production_order", ProposeOrderArgs, kind="action")
async def propose_production_order(ctx: ToolContext, args: ProposeOrderArgs) -> dict[str, Any]:
    # Права проверяем уже на этапе предложения — чтобы не показывать кнопку, которая всё равно не сработает.
    # При подтверждении сервис проверит их ещё раз.
    require(ctx.actor, Perm.MANAGE_ORDERS)
    if args.planned_date < today():
        raise DomainError("Дата задания не может быть в прошлом.")
    recipe = await catalog.find_recipe(ctx.session, ctx.actor, args.recipe)
    preview_rows = await orders.estimate_plan(ctx.session, ctx.actor, recipe_id=recipe.id, qty=args.qty)
    preview = {
        "title": f"Создать и запланировать задание: «{recipe.name}», {fmt_num(args.qty)} шт на "
        f"{args.planned_date:%d.%m.%Y}, цех {args.workshop}",
        "recipe": recipe.name,
        "qty": args.qty,
        "planned_date": args.planned_date.isoformat(),
        "workshop": args.workshop,
        "comment": args.comment,
        "components": [
            {k: str(v) if isinstance(v, Decimal) else v for k, v in r.items()} for r in preview_rows
        ],
        "has_shortage": any(r["shortage"] > 0 for r in preview_rows),
    }
    action = PendingAction(
        conversation_id=ctx.conversation_id,
        message_id=ctx.assistant_message_id,
        user_id=ctx.actor.user_id,
        kind="create_and_plan_order",
        payload={
            "recipe_id": recipe.id,
            "qty": args.qty,
            "planned_date": args.planned_date.isoformat(),
            "workshop": args.workshop,
            "comment": args.comment,
        },
        preview=preview,
    )
    ctx.session.add(action)
    await ctx.session.commit()
    ctx.actions.append({"id": action.id, "status": "pending", "kind": action.kind, "preview": preview})
    return {
        "status": "awaiting_user_confirmation",
        "action_id": action.id,
        "note": NOTES["order_not_created"],
        "preview": preview,
    }


# ---------- Память ----------


class FactArgs(Args):
    fact: str = Field(min_length=3, max_length=300)
    source_quote: str = Field(
        min_length=4,
        max_length=300,
    )


@tool("remember_fact", FactArgs, kind="memory")
async def remember_fact(ctx: ToolContext, args: FactArgs) -> dict[str, Any]:
    memory.check_quote(args.source_quote, ctx.user_message)
    fact = await memory.add_fact(ctx.session, ctx.actor, args.fact)
    return {"saved": True, "fact_id": fact.id, "fact": fact.text}


# ---------- Данные для Code Interpreter ----------

Dataset = Literal["consumption_by_week", "batches", "orders", "stock", "recipe_costs"]
EXPORT_MAX_ROWS = 5000


class ExportArgs(Args):
    dataset: Dataset
    date_from: date | None = Field(default=None)
    date_to: date | None = Field(default=None)
    material: str | None = Field(
        default=None,
        max_length=100,
    )


async def _dataset_rows(ctx: ToolContext, args: ExportArgs) -> list[dict[str, Any]]:
    current = today()
    d_from = args.date_from or current - timedelta(days=90)
    d_to = args.date_to or current
    if args.dataset == "consumption_by_week":
        return await reports.consumption_by_week(ctx.session, ctx.actor, d_from, d_to, args.material)
    if args.dataset == "stock":
        return await reports.material_stock(ctx.session, ctx.actor, args.material)
    if args.dataset == "batches":
        out = []
        show_cost = has_perm(ctx.actor, Perm.VIEW_COSTS) or has_perm(ctx.actor, Perm.CREATE_RECEIPT)
        rows: list = []
        page = 1
        while len(rows) <= EXPORT_MAX_ROWS:  # реестр отдаёт по 200 — собираем страницы до лимита
            chunk, total = await batches_service.list_batches(
                ctx.session,
                ctx.actor,
                BatchFilters(material=args.material, date_from=d_from, date_to=d_to),
                sort="received_date",
                direction="asc",
                page=page,
                page_size=200,
            )
            rows += chunk
            if not chunk or len(rows) >= total:
                break
            page += 1
        for b, m, s in rows:
            row = {
                "number": b.number,
                "received_date": b.received_date,
                "material_code": m.code,
                "material": m.name,
                "unit": m.unit,
                "supplier": s.name,
                "status": b.status,
                "qty": b.qty,
                "remaining": b.remaining_qty,
                "reserved": b.reserved_qty,
            }
            if show_cost:
                row |= {"price": b.price, "currency": b.currency, "unit_cost_rub": b.unit_cost_rub}
            out.append(row)
        return out
    if args.dataset == "orders":
        rows = await orders.list_orders(
            ctx.session,
            ctx.actor,
            date_from=d_from,
            date_to=d_to + timedelta(days=60),
            limit=EXPORT_MAX_ROWS + 1,
        )
        return [
            {
                "number": o.number,
                "product": o.recipe.name,
                "qty": o.qty,
                "planned_date": o.planned_date,
                "workshop": o.workshop,
                "status": o.status,
                "material": c.material.name,
                "unit": c.material.unit,
                "required": c.required_qty,
                "reserved": c.reserved_qty,
                "actual": c.actual_qty,
            }
            for o in rows
            for c in o.components
        ]
    if args.dataset == "recipe_costs":
        require(ctx.actor, Perm.VIEW_COSTS)
        avg = await _avg_unit_cost(ctx.session)
        out = []
        for r in await catalog.list_recipes(ctx.session, ctx.actor):
            for i in r.items:
                unit_cost = avg.get(i.material_id)
                out.append(
                    {
                        "recipe": r.name,
                        "material_code": i.material.code,
                        "material": i.material.name,
                        "unit": i.material.unit,
                        "qty_per_unit": i.qty_per_unit,
                        "avg_unit_cost_rub": unit_cost,
                        "cost_per_candle_rub": q_money(unit_cost * i.qty_per_unit)
                        if unit_cost is not None
                        else None,
                    }
                )
        return out
    raise DomainError("Неизвестный набор данных.")


async def _avg_unit_cost(session: AsyncSession) -> dict[int, Decimal]:
    """Средневзвешенная себестоимость единицы по всем принятым партиям (по полученному количеству)."""
    rows = await session.execute(
        select(Batch.material_id, func.sum(Batch.qty * Batch.unit_cost_rub) / func.sum(Batch.qty))
        .where(Batch.status == BatchStatus.ACCEPTED)
        .group_by(Batch.material_id)
    )
    return {mid: Decimal(v).quantize(Decimal("0.0001")) for mid, v in rows.all() if v is not None}


@tool("export_dataset", ExportArgs, kind="sandbox")
async def export_dataset(ctx: ToolContext, args: ExportArgs) -> dict[str, Any]:
    if ctx.sandbox is None or ctx.container_id is None:
        raise DomainError("Песочница для расчётов сейчас недоступна, выгрузить данные не получится.")
    rows = await _dataset_rows(ctx, args)
    if not rows:
        return {"rows": 0, "message": "За выбранный период данных нет — файл не создан."}
    total = len(rows)
    truncated = total > EXPORT_MAX_ROWS
    rows = rows[:EXPORT_MAX_ROWS]
    # Псевдонимы — до записи в файл: в песочнице не должно быть ПДн.
    masked = [ctx.pii.mask_obj({k: _cell(v) for k, v in r.items()}) for r in rows]
    columns = list(masked[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    writer.writerows(masked)
    filename = f"{args.dataset}_{today():%Y%m%d}.csv"
    try:
        path = await ctx.sandbox.upload(ctx.container_id, filename, buf.getvalue().encode("utf-8"))
    except SandboxError as exc:
        raise DomainError("Не удалось загрузить данные в песочницу. Попробуйте ещё раз.") from exc
    result: dict[str, Any] = {"path": path, "rows": len(masked), "columns": columns, "head": masked[:5]}
    if truncated:
        # Не обрезаем молча: модель должна сказать, что данные неполные.
        result["truncated"] = True
        result["truncated_note"] = Template(NOTES["export_truncated"]).safe_substitute(
            limit=EXPORT_MAX_ROWS, total=total
        )
    if args.material and args.dataset in ("recipe_costs", "orders"):
        result["note"] = NOTES["export_filter_ignored"]
    return result


def _cell(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


# ---------- Выполнение ----------


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any]
    summary: str


async def execute(ctx: ToolContext, name: str, raw_arguments: str) -> ToolResult:
    tool_ = REGISTRY.get(name)
    if tool_ is None:
        return ToolResult(False, {"error": f"Нет инструмента {name}"}, "неизвестный инструмент")
    try:
        parsed = json.loads(raw_arguments or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("arguments must be an object")
        # Модель оперирует псевдонимами — перед вызовом сервиса возвращаем настоящие значения.
        args = tool_.args_model.model_validate(ctx.pii.unmask_obj(parsed))
    except (ValueError, ValidationError) as exc:
        detail = exc.errors(include_url=False) if isinstance(exc, ValidationError) else str(exc)
        return ToolResult(
            False,
            {"error": "Некорректные аргументы инструмента", "detail": str(detail)[:500]},
            "некорректные аргументы",
        )
    try:
        data = await tool_.handler(ctx, args)
        return ToolResult(True, data, "ok")
    except Forbidden as exc:
        await ctx.session.rollback()
        return ToolResult(False, {"error": exc.message, "forbidden": True}, "нет прав")
    except DomainError as exc:
        await ctx.session.rollback()
        return ToolResult(False, {"error": exc.message}, exc.message[:120])
    except Exception:
        log.exception("tool %s failed", name)
        await ctx.session.rollback()
        return ToolResult(
            False,
            {"error": NOTES["tool_internal_error"]},
            "внутренняя ошибка",
        )


def specs() -> list[ToolSpec]:
    return [t.spec() for t in REGISTRY.values()]
