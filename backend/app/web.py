"""Граница HTTP: любые ошибки ввода превращаются в понятный текст по-русски, а не в 500.

* RequestValidationError (Pydantic) — переводим типовые сообщения и называем поле по-русски;
* 404/405 и другие ответы самого фреймворка — по-русски;
* NUL-байт (\\u0000) в адресе или JSON — отказ до бизнес-логики: PostgreSQL такие строки не хранит;
* страховка: если некорректное значение всё же дошло до базы (переполнение числа, int4), отвечаем 400.
"""

import json
import logging
import time
from http import HTTPStatus
from typing import Annotated, Any

import asyncpg.exceptions
import asyncpg.exceptions._base
from fastapi import Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

# Первичные ключи — integer (int4) в PostgreSQL.
MAX_ID = 2_147_483_647
Id = Annotated[int, Path(ge=1, le=MAX_ID)]
IdQuery = Annotated[int, Query(ge=1, le=MAX_ID)]
OptionalIdQuery = Annotated[int | None, Query(ge=1, le=MAX_ID)]

FIELD_NAMES = {
    "qty": "количество",
    "price": "цена",
    "currency": "валюта",
    "received_date": "дата поступления",
    "planned_date": "плановая дата",
    "supplier": "поставщик",
    "material_code": "код материала",
    "material": "материал",
    "recipe_id": "рецепт",
    "workshop": "цех",
    "text": "текст",
    "username": "логин",
    "password": "пароль",
    "name": "название",
    "code": "код",
    "unit": "единица измерения",
    "comment": "комментарий",
    "lines": "строки поступления",
    "items": "состав",
    "qty_per_unit": "норма на 1 шт",
    "actual": "фактический расход",
    "status": "статус",
    "sort": "сортировка",
    "direction": "направление сортировки",
    "date_from": "дата начала",
    "date_to": "дата окончания",
    "page": "страница",
    "page_size": "размер страницы",
    "file_ids": "файлы",
    "number": "номер",
    "entity_id": "идентификатор записи",
    "entity_type": "тип записи",
    "batch_id": "номер партии",
    "order_id": "номер задания",
    "report_id": "номер отчёта",
    "conversation_id": "диалог",
    "action_id": "действие",
    "file_id": "файл",
    "fact_id": "факт",
    "[key]": "идентификатор материала",
    "body": "тело запроса",
}


def _msg(err: dict[str, Any]) -> str:
    t, ctx = err.get("type", ""), err.get("ctx") or {}
    if t == "missing":
        return "обязательное поле"
    if t == "greater_than":
        return f"должно быть больше {ctx.get('gt')}"
    if t == "greater_than_equal":
        return f"должно быть не меньше {ctx.get('ge')}"
    if t == "less_than":
        return f"должно быть меньше {ctx.get('lt')}"
    if t == "less_than_equal":
        return f"должно быть не больше {ctx.get('le')}"
    if t == "string_too_short":
        n = ctx.get("min_length", 1)
        return "не может быть пустым" if n == 1 else f"не короче {n} символов"
    if t == "string_too_long":
        return f"не длиннее {ctx.get('max_length')} символов"
    if t == "too_short":
        return f"нужно хотя бы {ctx.get('min_length')} элемент(а)"
    if t == "too_long":
        return f"не больше {ctx.get('max_length')} элементов"
    if t in ("int_parsing", "int_type", "int_from_float"):
        return "должно быть целым числом"
    if t in ("float_parsing", "float_type", "decimal_parsing", "decimal_type", "finite_number"):
        return "должно быть числом"
    if t == "decimal_max_places":
        return f"не больше {ctx.get('decimal_places')} знаков после запятой"
    if t in ("decimal_max_digits", "decimal_whole_digits"):
        return "слишком большое число"
    if t.startswith("date") or t.startswith("datetime"):
        return "нужна дата в формате ГГГГ-ММ-ДД"
    if t in ("literal_error", "enum"):
        return f"допустимые значения: {ctx.get('expected')}"
    if t == "bool_parsing":
        return "должно быть «да» или «нет» (true/false)"
    if t == "json_invalid":
        return "некорректный JSON"
    if t == "list_type":
        return "должно быть списком"
    if t == "string_type":
        return "должно быть строкой"
    if t in ("dict_type", "model_type", "model_attributes_type"):
        return "неверный формат данных"
    if t == "extra_forbidden":
        return "лишнее поле"
    if t == "value_error":  # наши собственные проверки — их текст уже по-русски
        return str(err.get("msg", "")).removeprefix("Value error, ")
    return "некорректное значение"


def _field(loc: tuple) -> str:
    name = next(
        (str(p) for p in reversed(loc) if isinstance(p, str) and p not in ("body", "query", "path")), ""
    )
    if not name:
        name = "body" if loc and loc[0] == "body" else ""
    return FIELD_NAMES.get(name, name)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    parts = []
    for err in exc.errors()[:5]:
        field = _field(tuple(err.get("loc") or ()))
        parts.append(f"{field}: {_msg(err)}" if field else _msg(err))
    return JSONResponse({"detail": "Проверьте данные — " + "; ".join(parts)}, status_code=422)


HTTP_MESSAGES = {
    400: "Некорректный запрос.",
    401: "Нужно войти в систему.",
    403: "Недостаточно прав.",
    404: "Не найдено: такого адреса или объекта нет.",
    405: "Этот адрес не поддерживает такой запрос.",
    413: "Слишком большой запрос.",
    415: "Неподдерживаемый формат данных.",
    429: "Слишком много запросов, попробуйте чуть позже.",
}


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    # Стандартные английские фразы фреймворка («Not Found», «Method Not Allowed») — заменяем.
    if not isinstance(detail, str) or detail == HTTPStatus(exc.status_code).phrase:
        detail = HTTP_MESSAGES.get(exc.status_code, "Запрос не выполнен.")
    return JSONResponse({"detail": detail}, status_code=exc.status_code, headers=exc.headers)


# Неверное значение для колонки: переполнение числа, int4, недопустимый символ (класс SQLSTATE 22),
# а также ошибка кодирования параметра на стороне драйвера asyncpg.
_BAD_VALUE_ERRORS = (asyncpg.exceptions.DataError, asyncpg.exceptions._base.DataError)


def _is_bad_value(exc: BaseException) -> bool:
    seen: BaseException | None = getattr(exc, "orig", None) or exc
    for _ in range(6):
        if seen is None:
            return False
        if isinstance(seen, _BAD_VALUE_ERRORS):
            return True
        seen = seen.__cause__ or getattr(seen, "orig", None)
    return False


async def db_error_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    if _is_bad_value(exc):
        # Сюда попадает то, что не поймала валидация: значение не влезло в колонку, недопустимый символ.
        log.warning("bad value on %s %s: %s", request.method, request.url.path, type(exc.orig).__name__)
        return JSONResponse(
            {
                "detail": "Некорректное значение: число слишком большое или в тексте есть недопустимые символы."
            },
            status_code=400,
        )
    log.error("database error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        {"detail": "Внутренняя ошибка сервера. Мы уже записали её в журнал, попробуйте позже."},
        status_code=500,
    )


NUL_MESSAGE = "В данных есть недопустимый символ (NUL, \\u0000). Уберите его и повторите."


def _has_nul(value: Any) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_nul(k) or _has_nul(v) for k, v in value.items())
    if isinstance(value, list):
        return any(_has_nul(v) for v in value)
    return False


class RejectNulMiddleware:
    """NUL-байт в адресе, параметрах или JSON → 422 с текстом. PostgreSQL не хранит \\x00 в text."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        target = (scope.get("raw_path") or b"") + b"?" + (scope.get("query_string") or b"")
        if b"%00" in target or "\x00" in scope.get("path", ""):
            return await _reject(send)
        headers = dict(scope.get("headers") or [])
        if not headers.get(b"content-type", b"").startswith(b"application/json"):
            return await self.app(scope, receive, send)

        chunks, more = [], True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                return await self.app(scope, receive, send)
            chunks.append(message.get("body", b""))
            more = message.get("more_body", False)
        body = b"".join(chunks)
        if b"\x00" in body:
            return await _reject(send)
        if b"\\u0000" in body:
            try:
                if _has_nul(json.loads(body)):
                    return await _reject(send)
            except ValueError:
                pass  # некорректный JSON — ответит обычная валидация

        replayed = False

        async def replay():
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)


async def _reject(send) -> None:
    payload = json.dumps({"detail": NUL_MESSAGE}, ensure_ascii=False).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 422,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})


access_log = logging.getLogger("app.access")


class AccessLogMiddleware:
    """Журнал запросов: метод, путь, статус, время. Без query string — в параметрах бывают ПДн."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started = time.monotonic()
        status = 500

        async def send_wrapper(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            access_log.info(
                "%s %s %s %.0fms", scope["method"], scope["path"], status, (time.monotonic() - started) * 1000
            )
