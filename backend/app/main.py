import logging
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, chat, orders, warehouse
from app.config import get_settings
from app.errors import DomainError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse({"detail": exc.message}, status_code=exc.status_code)


FIELD_NAMES = {
    "qty": "количество",
    "price": "цена",
    "currency": "валюта",
    "received_date": "дата поступления",
    "planned_date": "плановая дата",
    "supplier": "поставщик",
    "material_code": "код материала",
    "recipe_id": "рецепт",
    "workshop": "цех",
    "text": "текст",
    "username": "логин",
    "password": "пароль",
}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    parts = []
    for err in exc.errors()[:5]:
        field = next((str(p) for p in reversed(err["loc"]) if isinstance(p, str)), "")
        parts.append(f"{FIELD_NAMES.get(field, field)}: {err['msg']}")
    return JSONResponse({"detail": "Проверьте данные — " + "; ".join(parts)}, status_code=422)


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
