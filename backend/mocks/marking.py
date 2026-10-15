"""Мок сервиса маркировки. Ведёт себя нестабильно, как и положено внешнему сервису:

* MARKING_FAILURE_RATE (по умолчанию 30%) запросов — 500 без обработки;
* MARKING_SLOW_RATE (10%) запросов — обрабатываются, но ответ приходит через MARKING_SLOW_SECONDS (10 с).
  Клиент к этому времени уже отвалится по таймауту и повторит запрос — тут и нужна идемпотентность;
* повтор с тем же Idempotency-Key возвращает уже созданный отчёт, дубль не создаётся.
"""

import asyncio
import os
import random
import uuid

from fastapi import FastAPI, Header, HTTPException

app = FastAPI(title="Mock: сервис маркировки")

FAILURE_RATE = float(os.getenv("MARKING_FAILURE_RATE", "0.3"))
SLOW_RATE = float(os.getenv("MARKING_SLOW_RATE", "0.1"))
SLOW_SECONDS = float(os.getenv("MARKING_SLOW_SECONDS", "10"))

reports: dict[str, dict] = {}
stats = {"requests": 0, "failed_500": 0, "slow": 0, "duplicates_prevented": 0}


@app.post("/reports")
async def create_report(payload: dict, idempotency_key: str | None = Header(default=None)) -> dict:
    stats["requests"] += 1
    if not idempotency_key:
        raise HTTPException(400, "Idempotency-Key header is required")
    if random.random() < FAILURE_RATE:
        stats["failed_500"] += 1
        raise HTTPException(500, "Internal error (mock)")
    if idempotency_key in reports:
        stats["duplicates_prevented"] += 1
        return reports[idempotency_key] | {"duplicate": True}
    record = {"id": str(uuid.uuid4()), "payload": payload}
    reports[idempotency_key] = record
    if random.random() < SLOW_RATE:
        stats["slow"] += 1
        await asyncio.sleep(SLOW_SECONDS)
    return record


@app.get("/reports")
def list_reports() -> dict:
    return {"count": len(reports), "stats": stats, "reports": list(reports.values())}


@app.get("/health")
def health() -> dict:
    return {"ok": True}
