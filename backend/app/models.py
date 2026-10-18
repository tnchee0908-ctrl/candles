"""ORM-модели. Схема БД создаётся только миграциями Alembic (alembic/versions)."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Количества — до 4 знаков (граммы в кг), деньги — до 2, курсы и себестоимость единицы — до 6.
Qty = Numeric(18, 4)
Money = Numeric(18, 2)
Rate = Numeric(18, 6)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[Any]: JSONB}


class Role(StrEnum):
    STOREKEEPER = "storekeeper"
    TECHNOLOGIST = "technologist"
    MANAGER = "manager"


ROLE_TITLES = {
    Role.STOREKEEPER: "Кладовщик",
    Role.TECHNOLOGIST: "Технолог",
    Role.MANAGER: "Руководитель",
}


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class BatchStatus(StrEnum):
    ON_CHECK = "on_check"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


BATCH_STATUS_TITLES = {
    BatchStatus.ON_CHECK: "На проверке",
    BatchStatus.ACCEPTED: "Принята",
    BatchStatus.REJECTED: "Брак",
}


class OrderStatus(StrEnum):
    DRAFT = "draft"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


ORDER_STATUS_TITLES = {
    OrderStatus.DRAFT: "Черновик",
    OrderStatus.PLANNED: "Запланировано",
    OrderStatus.IN_PROGRESS: "В работе",
    OrderStatus.COMPLETED: "Завершено",
    OrderStatus.CANCELLED: "Отменено",
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(256))


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    # Другие написания (латиницей / по-русски), по которым поставщика тоже нужно узнавать и маскировать.
    aliases: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(16))


class CurrencyRate(Base):
    """Кэш курсов из сервиса курсов: рублей за 1 единицу валюты на дату публикации."""

    __tablename__ = "currency_rates"
    __table_args__ = (UniqueConstraint("currency", "rate_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String(3))
    rate_date: Mapped[date] = mapped_column(Date)
    rate: Mapped[Decimal] = mapped_column(Rate)


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        server_default=text("'ПСТ-' || lpad(nextval('receipt_number_seq')::text, 5, '0')"),
    )
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    received_date: Mapped[date] = mapped_column(Date)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    supplier: Mapped[Supplier] = relationship()
    batches: Mapped[list["Batch"]] = relationship(back_populates="receipt")


class Batch(Base):
    __tablename__ = "batches"
    __table_args__ = (
        CheckConstraint("qty > 0", name="batch_qty_positive"),
        CheckConstraint("remaining_qty >= 0", name="batch_remaining_nonneg"),
        CheckConstraint("reserved_qty >= 0", name="batch_reserved_nonneg"),
        # Главный страховочный инвариант: нельзя зарезервировать больше, чем лежит в партии.
        CheckConstraint("reserved_qty <= remaining_qty", name="batch_reserved_le_remaining"),
        CheckConstraint("status IN ('on_check','accepted','rejected')", name="batch_status_valid"),
        CheckConstraint("currency IN ('RUB','USD','EUR')", name="batch_currency_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        server_default=text("'П-' || lpad(nextval('batch_number_seq')::text, 5, '0')"),
    )
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    received_date: Mapped[date] = mapped_column(Date, index=True)
    qty: Mapped[Decimal] = mapped_column(Qty)
    remaining_qty: Mapped[Decimal] = mapped_column(Qty)
    reserved_qty: Mapped[Decimal] = mapped_column(Qty, server_default="0")
    price: Mapped[Decimal] = mapped_column(Money)  # цена за единицу в валюте поступления
    currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(Rate)  # курс к рублю, 1 для RUB
    rate_date: Mapped[date] = mapped_column(Date)  # дата, чей курс реально применён
    unit_cost_rub: Mapped[Decimal] = mapped_column(Rate)
    status: Mapped[str] = mapped_column(String(16), server_default=BatchStatus.ON_CHECK.value)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    material: Mapped[Material] = relationship()
    receipt: Mapped[Receipt] = relationship(back_populates="batches")


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    items: Mapped[list["RecipeItem"]] = relationship(back_populates="recipe", cascade="all, delete-orphan")


class RecipeItem(Base):
    __tablename__ = "recipe_items"
    __table_args__ = (UniqueConstraint("recipe_id", "material_id"), CheckConstraint("qty_per_unit > 0"))

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    qty_per_unit: Mapped[Decimal] = mapped_column(Qty)

    recipe: Mapped[Recipe] = relationship(back_populates="items")
    material: Mapped[Material] = relationship()


class ProductionOrder(Base):
    __tablename__ = "production_orders"
    __table_args__ = (
        CheckConstraint("qty > 0", name="order_qty_positive"),
        CheckConstraint(
            "status IN ('draft','planned','in_progress','completed','cancelled')", name="order_status_valid"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        server_default=text("'З-' || lpad(nextval('order_number_seq')::text, 5, '0')"),
    )
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id"))
    qty: Mapped[int] = mapped_column(Integer)
    planned_date: Mapped[date] = mapped_column(Date, index=True)
    workshop: Mapped[int] = mapped_column(Integer, server_default="1")
    status: Mapped[str] = mapped_column(String(16), server_default=OrderStatus.DRAFT.value)
    comment: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recipe: Mapped[Recipe] = relationship()
    components: Mapped[list["OrderComponent"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="OrderComponent.id"
    )


class OrderComponent(Base):
    """Потребность задания в материале: норма рецепта × количество, зафиксированная при создании."""

    __tablename__ = "order_components"
    __table_args__ = (UniqueConstraint("order_id", "material_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id", ondelete="CASCADE"))
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    required_qty: Mapped[Decimal] = mapped_column(Qty)
    reserved_qty: Mapped[Decimal] = mapped_column(Qty, server_default="0")
    actual_qty: Mapped[Decimal | None] = mapped_column(Qty)

    order: Mapped[ProductionOrder] = relationship(back_populates="components")
    material: Mapped[Material] = relationship()


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (UniqueConstraint("order_id", "batch_id"), CheckConstraint("qty > 0"))

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    qty: Mapped[Decimal] = mapped_column(Qty)

    batch: Mapped[Batch] = relationship()


class Consumption(Base):
    """Фактическое списание из партии под задание (при завершении)."""

    __tablename__ = "consumptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"))
    qty: Mapped[Decimal] = mapped_column(Qty)
    unit_cost_rub: Mapped[Decimal] = mapped_column(Rate)
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    batch: Mapped[Batch] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    user_full_name: Mapped[str] = mapped_column(String(200))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int] = mapped_column(Integer)
    entity_label: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    via_assistant: Mapped[bool] = mapped_column(Boolean, server_default="false")


class MarkingReport(Base):
    """Исходящий отчёт в сервис маркировки (outbox). Создаётся в одной транзакции с завершением задания."""

    __tablename__ = "marking_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("production_orders.id"), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), server_default="pending")  # pending | sent | failed
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(64))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MarkingAttempt(Base):
    __tablename__ = "marking_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("marking_reports.id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status_code: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int] = mapped_column(Integer)


# ---------- ИИ-ассистент ----------


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200), server_default="Новый диалог")
    # Контейнер OpenAI Code Interpreter, живёт ~20 минут без активности, пересоздаётся при необходимости.
    container_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text, server_default="")
    # complete | interrupted (остановлен пользователем / оборвался) | error
    status: Mapped[str] = mapped_column(String(16), server_default="complete")
    model: Mapped[str | None] = mapped_column(String(64))
    # tool_calls: [{name, arguments, ok, summary}], code: [{code, outputs}], files: [ids], error
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PendingAction(Base):
    """Действие, предложенное ассистентом. Данные меняются только после «Подтвердить»."""

    __tablename__ = "pending_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    preview: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String(16), server_default="pending"
    )  # pending|confirmed|rejected|failed
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatFile(Base):
    __tablename__ = "chat_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    direction: Mapped[str] = mapped_column(String(16))  # upload | generated
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(128))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    container_path: Mapped[str | None] = mapped_column(String(512))  # путь файла в контейнере
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserFact(Base):
    __tablename__ = "user_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Pseudonym(Base):
    """Стабильный псевдоним сущности с ПДн: один сотрудник/поставщик — один псевдоним навсегда."""

    __tablename__ = "pseudonyms"
    __table_args__ = (UniqueConstraint("kind", "entity_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # person | supplier
    entity_id: Mapped[int] = mapped_column(Integer)
    alias: Mapped[str] = mapped_column(String(64), unique=True)
