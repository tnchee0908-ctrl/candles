import logging
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, update
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import auth, chat, orders, warehouse
from app.config import get_settings
from app.db import SessionLocal
from app.errors import DomainError
from app.models import Message
from app.web import (
    RejectNulMiddleware,
    db_error_handler,
    http_error_handler,
    validation_error_handler,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)


async def mark_stale_streams() -> None:
    """Если процесс упал посреди ответа, сообщение осталось в статусе streaming — помечаем прерванным."""
    async with SessionLocal() as session:
        await session.execute(
            update(Message)
            .where(Message.status == "streaming")
            .values(
                status="interrupted",
                meta=Message.meta.op("||")(
                    func.jsonb_build_object("error", "Ответ прерван: сервер был перезапущен.")
                ),
            )
        )
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mark_stale_streams()
    try:
        app.state.arq = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    except Exception:  # noqa: BLE001 — без Redis API работает, отчёты подберёт cron воркера
        log.warning("Redis недоступен, фоновые задачи будут подобраны воркером позже")
        app.state.arq = None
    yield
    if app.state.arq is not None:
        await app.state.arq.aclose()


app = FastAPI(
    title="Свечная мастерская: учёт и ИИ-ассистент",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"]
)
app.add_middleware(RejectNulMiddleware)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.add_exception_handler(DBAPIError, db_error_handler)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse({"detail": exc.message}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        {"detail": "Внутренняя ошибка сервера. Мы уже записали её в журнал, попробуйте позже."},
        status_code=500,
    )


app.include_router(auth.router)
app.include_router(warehouse.router)
app.include_router(orders.router)
app.include_router(chat.router)


@app.get("/api/health", tags=["system"])
async def health() -> dict:
    return {"ok": True}
