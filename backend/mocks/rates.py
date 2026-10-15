"""Мок сервиса курсов валют.

Курс публикуется только в рабочие дни (пн–пт) и не публикуется на будущие даты — на такие даты 404.
Значения детерминированные: один и тот же день всегда даёт один и тот же курс.
"""

import hashlib
from datetime import date
from decimal import Decimal

from fastapi import FastAPI, HTTPException, Query

app = FastAPI(title="Mock: курсы валют")

BASE = {"USD": Decimal("92.50"), "EUR": Decimal("100.20")}


def rate_for(currency: str, day: date) -> Decimal:
    # Плавный дрейф + детерминированный «шум» ±1.5 руб.
    seed = int(hashlib.sha256(f"{currency}:{day.isoformat()}".encode()).hexdigest()[:8], 16)
    noise = Decimal(seed % 3000 - 1500) / Decimal(1000)
    drift = Decimal(day.toordinal() % 60) / Decimal(20)
    return (BASE[currency] + drift + noise).quantize(Decimal("0.0001"))


@app.get("/rates")
def get_rate(currency: str = Query(pattern="^(USD|EUR)$"), date_: date = Query(alias="date")) -> dict:
    if date_.weekday() >= 5:
        raise HTTPException(404, "Курс на выходной день не публикуется")
    if date_ > date.today():
        raise HTTPException(404, "Курс ещё не опубликован")
    return {"currency": currency, "date": date_.isoformat(), "rate": str(rate_for(currency, date_))}


@app.get("/health")
def health() -> dict:
    return {"ok": True}
