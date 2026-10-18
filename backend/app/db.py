from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

# hide_parameters: в тексте ошибок SQLAlchemy (и в журнале) нет значений запроса — там бывают ФИО.
engine = create_async_engine(get_settings().database_url, pool_pre_ping=True, hide_parameters=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
