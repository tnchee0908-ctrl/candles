from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog
from app.services.common import Actor, to_jsonable
from app.services.permissions import Perm, require


def record(
    session: AsyncSession,
    actor: Actor,
    *,
    entity_type: str,
    entity_id: int,
    entity_label: str | None,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    """Пишет запись журнала в текущую транзакцию: изменение и его след фиксируются вместе или не фиксируются."""
    session.add(
        AuditLog(
            user_id=actor.user_id,
            user_full_name=actor.full_name,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_label=entity_label,
            action=action,
            before=to_jsonable(before) if before is not None else None,
            after=to_jsonable(after) if after is not None else None,
            via_assistant=actor.via_assistant,
        )
    )


async def list_entries(
    session: AsyncSession,
    actor: Actor,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    via_assistant: bool | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditLog], int]:
    require(actor, Perm.VIEW_AUDIT)
    stmt: Select = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if via_assistant is not None:
        stmt = stmt.where(AuditLog.via_assistant == via_assistant)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await session.scalars(
        stmt.order_by(AuditLog.at.desc(), AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(rows), int(total or 0)


async def entries_for(session: AsyncSession, entity_type: str, entity_id: int) -> list[AuditLog]:
    """История конкретной сущности (для карточек) — видна всем, кто видит саму сущность."""
    rows = await session.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.at, AuditLog.id)
    )
    return list(rows)
