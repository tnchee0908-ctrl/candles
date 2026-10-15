"""Фоновые задачи (arq + Redis).

Задача send_marking_report ставится сразу после завершения задания; cron poll_marking раз в 5 секунд
подбирает отчёты, у которых подошло время повтора (или которые не удалось поставить в очередь).
"""

import logging

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.db import SessionLocal
from app.services import marking

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


async def send_marking_report(ctx: dict, report_id: int) -> str:
    async with SessionLocal() as session:
        return await marking.send_report(session, report_id)


async def poll_marking(ctx: dict) -> int:
    async with SessionLocal() as session:
        ids = await marking.due_report_ids(session)
    for report_id in ids:
        async with SessionLocal() as session:
            await marking.send_report(session, report_id)
    return len(ids)


class WorkerSettings:
    functions = [send_marking_report]
    cron_jobs = [cron(poll_marking, second=set(range(0, 60, 5)), run_at_startup=True)]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    # Мок отвечает до 10 с, таймаут клиента 5 с — с запасом.
    job_timeout = 60
    max_jobs = 10
