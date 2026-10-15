"""Память ассистента: факты о конкретном пользователе.

Все функции принимают user_id и фильтруют по нему — факты одного пользователя никогда
не попадают в промпт другого.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import DomainError, NotFound
from app.models import UserFact

MAX_FACTS = 30
MAX_FACT_LEN = 300


async def list_facts(session: AsyncSession, user_id: int) -> list[UserFact]:
    return list(
        await session.scalars(select(UserFact).where(UserFact.user_id == user_id).order_by(UserFact.id))
    )


async def add_fact(session: AsyncSession, user_id: int, text: str) -> UserFact:
    text = " ".join(text.split())
    if not text:
        raise DomainError("Пустой факт.")
    if len(text) > MAX_FACT_LEN:
        raise DomainError(f"Факт длиннее {MAX_FACT_LEN} символов.")
    existing = await session.scalar(
        select(UserFact).where(UserFact.user_id == user_id, func.lower(UserFact.text) == text.lower())
    )
    if existing:
        return existing
    count = await session.scalar(
        select(func.count()).select_from(UserFact).where(UserFact.user_id == user_id)
    )
    if (count or 0) >= MAX_FACTS:
        raise DomainError(f"В памяти уже {MAX_FACTS} фактов — удалите ненужные на странице «Память».")
    fact = UserFact(user_id=user_id, text=text)
    session.add(fact)
    await session.commit()
    return fact


async def delete_fact(session: AsyncSession, user_id: int, fact_id: int) -> None:
    result = await session.execute(
        delete(UserFact).where(UserFact.id == fact_id, UserFact.user_id == user_id)
    )
    if result.rowcount == 0:
        raise NotFound("Факт не найден.")
    await session.commit()
