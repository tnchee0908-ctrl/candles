"""Отправка отчёта о выпуске в сервис маркировки.

Схема transactional outbox: при завершении задания в той же транзакции создаётся MarkingReport.
Завершение не ждёт сервис. Фоновая задача отправляет отчёт; при 5xx/таймауте/сетевой ошибке —
повтор с экспоненциально растущей паузой (+ случайный разброс). Каждая попытка пишется в журнал.
Заголовок Idempotency-Key одинаков во всех попытках, поэтому сервис не создаст дубль,
даже если первый ответ потерялся по таймауту, а запрос на самом деле дошёл.
"""

import logging
import random
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import MarkingAttempt, MarkingReport

log = logging.getLogger(__name__)


def backoff_delay(attempt: int, base: float, cap: float) -> float:
    """attempt=1 → ~base, 2 → ~2·base, 3 → ~4·base … не больше cap. Разброс ±20%, чтобы повторы не шли пачкой."""
    delay = min(cap, base * (2 ** (attempt - 1)))
    return delay * random.uniform(0.8, 1.2)


async def send_report(
    session: AsyncSession, report_id: int, transport: httpx.AsyncBaseTransport | None = None
) -> str:
    """Одна попытка отправки. Возвращает итоговый статус отчёта: sent | pending | failed."""
    settings = get_settings()
    report = await session.scalar(
        select(MarkingReport).where(MarkingReport.id == report_id).with_for_update(skip_locked=True)
    )
    if report is None:
        return "locked"  # отчёт уже обрабатывает другой воркер
    if report.status != "pending":
        return report.status

    attempt_no = report.attempts + 1
    started = time.monotonic()
    status_code: int | None = None
    error: str | None = None
    try:
        async with httpx.AsyncClient(
            base_url=settings.marking_service_url, timeout=settings.marking_timeout_s, transport=transport
        ) as client:
            resp = await client.post(
                "/reports", json=report.payload, headers={"Idempotency-Key": report.idempotency_key}
            )
        status_code = resp.status_code
        if resp.status_code < 300:
            report.status = "sent"
            report.sent_at = datetime.now(UTC)
            report.external_id = str(resp.json().get("id"))
        elif 400 <= resp.status_code < 500 and resp.status_code not in (408, 429):
            # Ошибка самого запроса — повтор не поможет.
            error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            report.status = "failed"
        else:
            error = f"HTTP {resp.status_code}"
    except httpx.TimeoutException:
        error = f"Таймаут {settings.marking_timeout_s} с"
    except httpx.HTTPError as exc:
        error = f"Сетевая ошибка: {exc.__class__.__name__}"

    duration_ms = int((time.monotonic() - started) * 1000)
    report.attempts = attempt_no
    report.last_error = error
    if report.status == "pending":
        if attempt_no >= settings.marking_max_attempts:
            report.status = "failed"
        else:
            delay = backoff_delay(attempt_no, settings.marking_base_delay_s, settings.marking_max_delay_s)
            report.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
    session.add(
        MarkingAttempt(
            report_id=report.id,
            attempt_no=attempt_no,
            status_code=status_code,
            error=error,
            duration_ms=duration_ms,
        )
    )
    await session.commit()
    log.info(
        "marking report=%s attempt=%s status=%s code=%s", report.id, attempt_no, report.status, status_code
    )
    return report.status


async def due_report_ids(session: AsyncSession, limit: int = 20) -> list[int]:
    rows = await session.scalars(
        select(MarkingReport.id)
        .where(MarkingReport.status == "pending", MarkingReport.next_attempt_at <= datetime.now(UTC))
        .order_by(MarkingReport.next_attempt_at)
        .limit(limit)
    )
    return list(rows)


async def retry_report(session: AsyncSession, report_id: int) -> MarkingReport | None:
    """Ручной перезапуск неудавшейся отправки (тот же ключ идемпотентности)."""
    report = await session.get(MarkingReport, report_id)
    if report is None:
        return None
    if report.status == "failed":
        report.status = "pending"
        report.next_attempt_at = datetime.now(UTC)
        await session.commit()
    return report
