"""Отправка в маркировку: повтор без дубля, растущая пауза, журнал попыток, 4xx не повторяется."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
from sqlalchemy import select

from app.models import MarkingAttempt, MarkingReport
from app.services import marking, orders
from app.services.common import today
from mocks import marking as marking_mock
from tests.conftest import add_batch


class LostResponseOnce(httpx.AsyncBaseTransport):
    """Первый запрос доходит до сервиса и обрабатывается, но ответ «теряется» (таймаут у клиента)."""

    def __init__(self, inner: httpx.AsyncBaseTransport):
        self.inner = inner
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        response = await self.inner.handle_async_request(request)
        if self.calls == 1:
            raise httpx.ReadTimeout("response lost", request=request)
        return response


class Always(httpx.AsyncBaseTransport):
    def __init__(self, status: int):
        self.status = status

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(self.status, json={"error": "x"})


async def completed_order_report(session, world) -> MarkingReport:
    await add_batch(session, world, world.wax, "10", days_ago=3)
    await add_batch(session, world, world.wick, "10", days_ago=3)
    tech = world.actors["tech"]
    result = await orders.create_and_plan(
        session, tech, recipe_id=world.recipe.id, qty=2, planned_date=today() + timedelta(days=1)
    )
    await orders.start_order(session, tech, result.order.id)
    await orders.complete_order(
        session, tech, result.order.id, {world.wax.id: Decimal(1), world.wick.id: Decimal(2)}
    )
    report = await session.scalar(select(MarkingReport).where(MarkingReport.order_id == result.order.id))
    assert report is not None
    return report


async def test_retry_after_lost_response_creates_no_duplicate(session, world, monkeypatch):
    monkeypatch.setattr(marking_mock, "FAILURE_RATE", 0.0)
    monkeypatch.setattr(marking_mock, "SLOW_RATE", 0.0)
    marking_mock.reports.clear()
    transport = LostResponseOnce(httpx.ASGITransport(app=marking_mock.app))
    report = await completed_order_report(session, world)

    first = await marking.send_report(session, report.id, transport=transport)
    assert first == "pending"  # таймаут → повтор позже
    await session.execute(
        MarkingReport.__table__.update()
        .where(MarkingReport.id == report.id)
        .values(next_attempt_at=datetime.now(UTC))
    )
    await session.commit()
    second = await marking.send_report(session, report.id, transport=transport)
    assert second == "sent"

    assert len(marking_mock.reports) == 1  # сервис получил отчёт дважды, но создал один
    assert marking_mock.stats["duplicates_prevented"] >= 1
    attempts = list(
        await session.scalars(select(MarkingAttempt).where(MarkingAttempt.report_id == report.id))
    )
    assert [a.attempt_no for a in attempts] == [1, 2]
    assert attempts[0].error and "Таймаут" in attempts[0].error


async def test_5xx_is_retried_with_growing_delay(session, world):
    report = await completed_order_report(session, world)
    delays = []
    for _ in range(3):
        before = datetime.now(UTC)
        status = await marking.send_report(session, report.id, transport=Always(500))
        assert status == "pending"
        await session.refresh(report)
        delays.append((report.next_attempt_at - before).total_seconds())
    assert delays[0] < delays[1] < delays[2]
    assert report.attempts == 3


async def test_4xx_is_not_retried(session, world):
    report = await completed_order_report(session, world)
    assert await marking.send_report(session, report.id, transport=Always(422)) == "failed"


def test_backoff_is_capped():
    assert marking.backoff_delay(30, base=2, cap=300) <= 300 * 1.2
