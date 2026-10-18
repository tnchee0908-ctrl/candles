from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.web import MAX_ID

DbId = Annotated[int, Field(ge=1, le=MAX_ID)]
# Пределы ниже — с запасом под колонки numeric(18, 4/6): иначе себестоимость в рублях переполнится.
MAX_QTY = Decimal("1000000000")
MAX_PRICE = Decimal("100000000")

# Decimal в JSON отдаём строкой: так не теряется точность (0.1 + 0.2), фронт форматирует сам.
Dec = Annotated[Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")]


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    role_title: str
    permissions: list[str]


class LoginOut(BaseModel):
    token: str
    user: UserOut


class MaterialIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    unit: str = Field(min_length=1, max_length=16)


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    unit: str


class StockOut(BaseModel):
    material_code: str
    material: str
    unit: str
    on_hand: Dec
    reserved: Dec
    free: Dec
    awaiting_inspection: Dec
    batches_with_stock: int


class RecipeItemIn(BaseModel):
    material_code: str
    qty_per_unit: Decimal = Field(gt=0, le=Decimal("10000"), max_digits=18, decimal_places=4)


class RecipeIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    items: list[RecipeItemIn] = Field(min_length=1)


class RecipeItemOut(BaseModel):
    material: MaterialOut
    qty_per_unit: Dec


class RecipeOut(BaseModel):
    id: int
    name: str
    items: list[RecipeItemOut]


class ReceiptLineIn(BaseModel):
    material_code: str = Field(min_length=1)
    qty: Decimal = Field(gt=0, le=MAX_QTY, max_digits=18, decimal_places=4)
    price: Decimal = Field(ge=0, le=MAX_PRICE, max_digits=18, decimal_places=2)
    currency: Literal["RUB", "USD", "EUR"]
    comment: str | None = Field(default=None, max_length=1000)


class ReceiptIn(BaseModel):
    supplier: str = Field(min_length=1, max_length=200)
    received_date: date
    lines: list[ReceiptLineIn] = Field(min_length=1, max_length=100)


class BatchRef(BaseModel):
    id: int
    number: str


class ReceiptOut(BaseModel):
    id: int
    number: str
    batch_numbers: list[str]
    batches: list[BatchRef]


class BatchRow(BaseModel):
    id: int
    number: str
    received_date: date
    material_code: str
    material: str
    unit: str
    supplier: str
    qty: Dec
    remaining_qty: Dec
    reserved_qty: Dec
    free_qty: Dec
    price: Dec
    currency: str
    rate: Dec
    rate_date: date
    unit_cost_rub: Dec
    status: str
    status_title: str
    comment: str | None


class Page(BaseModel):
    total: int
    page: int
    page_size: int


class BatchPage(Page):
    items: list[BatchRow]


class BatchStatusIn(BaseModel):
    status: Literal["accepted", "rejected"]


class AuditOut(BaseModel):
    id: int
    at: datetime
    user_full_name: str
    entity_type: str
    entity_id: int
    entity_label: str | None
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    via_assistant: bool


class AuditPage(Page):
    items: list[AuditOut]


class MovementOut(BaseModel):
    order_id: int
    order_number: str
    qty: Dec
    at: datetime | None = None


class BatchCard(BaseModel):
    batch: BatchRow
    receipt_number: str
    reservations: list[MovementOut]
    consumptions: list[MovementOut]
    history: list[AuditOut]


class OrderIn(BaseModel):
    recipe_id: DbId
    qty: int = Field(gt=0, le=100_000)
    planned_date: date
    workshop: int = Field(default=1, ge=1, le=3)
    comment: str | None = Field(default=None, max_length=1000)
    plan_now: bool = True


ActualQty = Annotated[Decimal, Field(ge=0, le=Decimal("1000000"), max_digits=18, decimal_places=4)]


class CompleteIn(BaseModel):
    # material_id -> фактический расход
    actual: dict[DbId, ActualQty]


class ComponentOut(BaseModel):
    material_id: int
    material_code: str
    material: str
    unit: str
    required_qty: Dec
    reserved_qty: Dec
    missing_qty: Dec
    actual_qty: Dec | None
    light: Literal["green", "yellow", "red"]


class OrderRow(BaseModel):
    id: int
    number: str
    product: str
    recipe_id: int
    qty: int
    planned_date: date
    workshop: int
    status: str
    status_title: str
    light: Literal["green", "yellow", "red"]
    # Коротко о дефиците для списка: «20,324 кг «Воск кокосовый»» (+ «и ещё N»)
    deficit_summary: str | None = None


class ReservationOut(BaseModel):
    batch_id: int
    batch_number: str
    material_id: int
    qty: Dec
    received_date: date


class MarkingAttemptOut(BaseModel):
    attempt_no: int
    at: datetime
    status_code: int | None
    error: str | None
    duration_ms: int


class MarkingOut(BaseModel):
    id: int
    order_id: int
    order_number: str | None = None
    product: str | None = None
    qty: int | None = None
    completed_at: datetime | None = None
    status: str
    attempts: int
    next_attempt_at: datetime | None
    last_error: str | None
    external_id: str | None
    sent_at: datetime | None
    idempotency_key: str
    attempt_log: list[MarkingAttemptOut] = []


class OrderCard(OrderRow):
    comment: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    components: list[ComponentOut]
    reservations: list[ReservationOut]
    consumptions: list[ReservationOut]
    history: list[AuditOut]
    marking: MarkingOut | None


class PlanPreviewRow(BaseModel):
    material_code: str
    material: str
    unit: str
    required: Dec
    free_now: Dec
    will_reserve: Dec
    shortage: Dec
