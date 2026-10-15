"""Курсы валют из внешнего (мок) сервиса с кэшем в БД.

Сервис публикует курс только в рабочие дни. Если на дату курса нет (выходной/праздник),
берём последний предыдущий опубликованный курс.
"""

from datetime import date, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.errors import DomainError
from app.models import Currency, CurrencyRate

MAX_LOOKBACK_DAYS = 14


class RatesClient:
    def __init__(self, base_url: str | None = None, timeout: float = 5.0):
        self.base_url = base_url or get_settings().rates_service_url
        self.timeout = timeout

    async def fetch(self, currency: str, on_date: date) -> Decimal | None:
        """Курс, опубликованный ровно на эту дату, или None, если на дату курса нет."""
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            resp = await client.get("/rates", params={"currency": currency, "date": on_date.isoformat()})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return Decimal(str(resp.json()["rate"]))


async def get_rate(
    session: AsyncSession, currency: str, on_date: date, client: RatesClient | None = None
) -> tuple[Decimal, date]:
    """Возвращает (курс, дата курса). Для RUB — (1, on_date)."""
    if currency == Currency.RUB:
        return Decimal(1), on_date
    if currency not in Currency.__members__.values():
        raise DomainError(f"Неизвестная валюта: {currency}")

    client = client or RatesClient()
    day = on_date
    for _ in range(MAX_LOOKBACK_DAYS):
        cached = await session.scalar(
            select(CurrencyRate).where(CurrencyRate.currency == currency, CurrencyRate.rate_date == day)
        )
        if cached:
            return cached.rate, day
        try:
            rate = await client.fetch(currency, day)
        except httpx.HTTPError as exc:
            raise DomainError(
                f"Сервис курсов валют недоступен, не удалось получить курс {currency} на {day:%d.%m.%Y}. "
                "Повторите позже."
            ) from exc
        if rate is not None:
            await session.execute(
                insert(CurrencyRate)
                .values(currency=currency, rate_date=day, rate=rate)
                .on_conflict_do_nothing(index_elements=["currency", "rate_date"])
            )
            return rate, day
        day -= timedelta(days=1)
    raise DomainError(f"Нет курса {currency} за {MAX_LOOKBACK_DAYS} дней до {on_date:%d.%m.%Y}.")
