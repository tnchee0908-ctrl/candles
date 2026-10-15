"""Лимит сообщений ассистенту: по пользователю в час и общий в сутки."""

from datetime import UTC, datetime, timedelta

import pytest

from app.assistant.quota import check_chat_quota
from app.errors import RateLimited
from app.models import Conversation, Message


async def add_user_messages(session, user, count: int, minutes_ago: int = 5) -> None:
    conv = Conversation(user_id=user.id)
    session.add(conv)
    await session.flush()
    at = datetime.now(UTC) - timedelta(minutes=minutes_ago)
    session.add_all(
        Message(conversation_id=conv.id, role="user", content=f"вопрос {i}", created_at=at)
        for i in range(count)
    )
    session.add(Message(conversation_id=conv.id, role="assistant", content="ответ", created_at=at))
    await session.commit()


async def test_hourly_limit_is_per_user(session, world):
    tech, boss = world.users["tech"], world.users["boss"]
    await add_user_messages(session, tech, 3, minutes_ago=20)
    with pytest.raises(RateLimited) as exc:
        await check_chat_quota(session, tech.id, per_user_hourly=3, total_daily=0)
    assert "не больше 3 в час" in exc.value.message
    assert "через 40 мин" in exc.value.message
    await check_chat_quota(
        session, boss.id, per_user_hourly=3, total_daily=0
    )  # другой пользователь не затронут


async def test_old_messages_do_not_count(session, world):
    await add_user_messages(session, world.users["tech"], 5, minutes_ago=90)
    await check_chat_quota(session, world.users["tech"].id, per_user_hourly=3, total_daily=0)


async def test_daily_limit_is_shared(session, world):
    await add_user_messages(session, world.users["tech"], 2)
    await add_user_messages(session, world.users["boss"], 2)
    with pytest.raises(RateLimited):
        await check_chat_quota(session, world.users["sklad"].id, per_user_hourly=0, total_daily=4)


async def test_zero_means_no_limit(session, world):
    await add_user_messages(session, world.users["tech"], 50)
    await check_chat_quota(session, world.users["tech"].id, per_user_hourly=0, total_daily=0)
