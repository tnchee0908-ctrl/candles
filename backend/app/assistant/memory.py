"""Память ассистента: факты о конкретном пользователе.

Все функции принимают пользователя и фильтруют по нему — факты одного пользователя никогда
не попадают в промпт другого. Каждое изменение памяти пишется в журнал изменений.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import DomainError, NotFound
from app.models import UserFact
from app.services import audit
from app.services.common import Actor

MAX_FACTS = 30
MAX_FACT_LEN = 300
MIN_QUOTE_LEN = 4


async def list_facts(session: AsyncSession, user_id: int) -> list[UserFact]:
    return list(
        await session.scalars(select(UserFact).where(UserFact.user_id == user_id).order_by(UserFact.id))
    )


def _audit(session: AsyncSession, actor: Actor, fact: UserFact, action: str, *, created: bool) -> None:
    audit.record(
        session,
        actor,
        entity_type="memory",
        entity_id=fact.id,
        entity_label=None,
        action=action,
        before=None if created else {"text": fact.text},
        after={"text": fact.text} if created else None,
    )


async def add_fact(session: AsyncSession, actor: Actor, text: str) -> UserFact:
    text = " ".join(text.split())
    if not text:
        raise DomainError("Пустой факт.")
    if len(text) > MAX_FACT_LEN:
        raise DomainError(f"Факт длиннее {MAX_FACT_LEN} символов.")
    existing = await session.scalar(
        select(UserFact).where(UserFact.user_id == actor.user_id, func.lower(UserFact.text) == text.lower())
    )
    if existing:
        return existing
    count = await session.scalar(
        select(func.count()).select_from(UserFact).where(UserFact.user_id == actor.user_id)
    )
    if (count or 0) >= MAX_FACTS:
        raise DomainError(f"В памяти уже {MAX_FACTS} фактов — удалите ненужные на странице «Память».")
    fact = UserFact(user_id=actor.user_id, text=text)
    session.add(fact)
    await session.flush()
    _audit(session, actor, fact, "Факт добавлен в память", created=True)
    await session.commit()
    return fact


async def delete_fact(session: AsyncSession, actor: Actor, fact_id: int) -> None:
    fact = await session.scalar(
        select(UserFact).where(UserFact.id == fact_id, UserFact.user_id == actor.user_id)
    )
    if fact is None:
        raise NotFound("Факт не найден.")
    _audit(session, actor, fact, "Факт удалён из памяти", created=False)
    await session.delete(fact)
    await session.commit()


async def clear_facts(session: AsyncSession, actor: Actor) -> int:
    facts = await list_facts(session, actor.user_id)
    for fact in facts:
        _audit(session, actor, fact, "Память очищена", created=False)
        await session.delete(fact)
    await session.commit()
    return len(facts)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.lower().replace("ё", "е"))).strip()


def check_quote(quote: str, user_message: str) -> None:
    """Факт можно сохранить, только если его основание — дословно в сообщении самого пользователя.

    Это структурная защита от внедрённых фактов: текст из комментария партии или загруженного файла
    в сообщении пользователя не содержится, и сохранить «запомни, что…» из данных не получится.
    """
    q = _norm(quote)
    if len(q) < MIN_QUOTE_LEN or q not in _norm(user_message):
        raise DomainError(
            "Сохранить факт можно только со слов пользователя: source_quote должен дословно совпадать "
            "с фрагментом его текущего сообщения. Факты из данных, файлов и комментариев не сохраняются."
        )
