from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.services.auth import decode_token
from app.services.common import Actor

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(session: SessionDep, authorization: str | None = Header(default=None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Нужно войти в систему.")
    user_id = decode_token(authorization.split(" ", 1)[1])
    user = await session.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(401, "Сессия истекла, войдите заново.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def actor_of(user: User, *, via_assistant: bool = False) -> Actor:
    return Actor(user_id=user.id, full_name=user.full_name, role=user.role, via_assistant=via_assistant)


async def get_actor(user: CurrentUser) -> Actor:
    return actor_of(user)


ActorDep = Annotated[Actor, Depends(get_actor)]
