"""Лимиты на сообщения ассистенту — защита бюджета ключа OpenAI на публичном стенде.

Считаем по базе (сообщения пользователя за скользящее окно), без отдельного хранилища:
лимит переживает перезапуск и работает при нескольких процессах API. 0 — без лимита.
"""

import math
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import RateLimited
from app.models import Conversation, Message

HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


async def check_chat_quota(
    session: AsyncSession,
    user_id: int,
    *,
    per_user_hourly: int,
    total_daily: int,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    if per_user_hourly:
        since = now - HOUR
        count, oldest = (
            await session.execute(
                select(func.count(), func.min(Message.created_at))
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(Conversation.user_id == user_id, Message.role == "user", Message.created_at >= since)
            )
        ).one()
        if count >= per_user_hourly:
            wait = max(1, math.ceil(((oldest + HOUR) - now).total_seconds() / 60))
            raise RateLimited(
                f"Лимит ассистента исчерпан: не больше {per_user_hourly} в час. "
                f"Следующее сообщение можно отправить через {wait} мин."
            )
    if total_daily:
        count = await session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.role == "user", Message.created_at >= now - DAY)
        )
        if (count or 0) >= total_daily:
            raise RateLimited(
                "Дневной лимит запросов к ассистенту на этом стенде исчерпан. Попробуйте завтра."
            )
