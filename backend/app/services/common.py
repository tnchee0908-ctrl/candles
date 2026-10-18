from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

QTY_STEP = Decimal("0.0001")
# Мастерская работает по Москве: «сегодня», «эта неделя», «пятница» и дата поступления по умолчанию
# считаются по местному времени, а не по UTC контейнера (иначе с 00:00 до 03:00 МСК был бы «вчерашний» день).
BUSINESS_TZ = ZoneInfo("Europe/Moscow")
MONEY_STEP = Decimal("0.01")


@dataclass(frozen=True)
class Actor:
    """Кто выполняет действие. Один и тот же объект приходит и от кнопки, и от ассистента."""

    user_id: int
    full_name: str
    role: str
    via_assistant: bool = False


def today() -> date:
    return datetime.now(BUSINESS_TZ).date()


def q_qty(value: Decimal) -> Decimal:
    return value.quantize(QTY_STEP, rounding=ROUND_HALF_UP)


def q_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)


def fmt_num(value: Decimal | int | None) -> str:
    """Человеческая запись числа для сообщений: 2.5000 -> «2,5», 1200 -> «1 200»."""
    if value is None:
        return "—"
    d = Decimal(value).normalize()
    if d == d.to_integral():
        d = d.quantize(Decimal(1))
    sign = "-" if d < 0 else ""
    s = f"{abs(d):f}"
    int_part, _, frac = s.partition(".")
    groups = []
    while len(int_part) > 3:
        groups.insert(0, int_part[-3:])
        int_part = int_part[:-3]
    groups.insert(0, int_part)
    out = " ".join(groups)
    return sign + (f"{out},{frac}" if frac else out)


def to_jsonable(value: Any) -> Any:
    """Decimal/дата -> строка, чтобы класть снимки в JSONB журнала без потери точности."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(v) for v in value]
    return value
