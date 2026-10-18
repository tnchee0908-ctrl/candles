"""Граница API: некорректный ввод → понятный текст по-русски, никогда не 500."""

import re
from datetime import date

import httpx
import pytest

from app.db import get_session
from app.main import app
from app.services.auth import create_token

TOO_BIG = 2_147_483_648  # int4 + 1
ENGLISH = re.compile(r"Input should|Field required|Not Found|Method Not Allowed|value is not", re.I)


@pytest.fixture
async def client(world, session_factory):
    async def test_session():
        async with session_factory() as s:
            yield s

    # Глобальный engine приложения привязан к другому event loop — подменяем сессию тестовой.
    app.dependency_overrides[get_session] = test_session
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    token = create_token(world.users["boss"])
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as c:
        yield c
    app.dependency_overrides.clear()


def assert_human(resp: httpx.Response, status: int) -> str:
    assert resp.status_code == status, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and not ENGLISH.search(detail), detail
    return detail


async def test_every_id_route_rejects_too_big_id(client):
    """Обходим все маршруты с {..._id} в адресе: на id больше int4 — 422 с текстом, а не 500."""
    checked = 0
    for route in app.routes:
        path = getattr(route, "path", "")
        if "_id}" not in path:
            continue
        url = re.sub(r"\{\w+_id\}", str(TOO_BIG), path)
        for method in route.methods - {"HEAD", "OPTIONS"}:
            resp = await client.request(method, url, json={})
            assert resp.status_code != 500, f"{method} {url}: {resp.text}"
            assert resp.status_code in (404, 422), f"{method} {url}: {resp.status_code}"
            checked += 1
    assert checked >= 18
    for url in (f"/api/audit?entity_id={TOO_BIG}", f"/api/orders/preview?recipe_id={TOO_BIG}&qty=1"):
        assert_human(await client.get(url), 422)


async def test_too_big_id_has_russian_text(client):
    detail = assert_human(await client.get(f"/api/batches/{TOO_BIG}"), 422)
    assert "номер партии" in detail


async def test_missing_object_and_unknown_route_are_russian(client):
    assert "не найден" in assert_human(await client.get("/api/batches/999999"), 404).lower()
    assert_human(await client.get("/api/no-such-thing"), 404)
    assert_human(await client.delete("/api/auth/me"), 405)


@pytest.mark.parametrize(
    "method,url,body",
    [
        ("post", "/api/chat/memory", {"text": "пиши\u0000коротко"}),
        ("post", "/api/auth/login", {"username": "boss\u0000", "password": "x"}),
        ("post", "/api/materials", {"code": "X1", "name": "Воск\u0000", "unit": "кг"}),
        ("get", "/api/batches?supplier=%00", None),
        ("get", "/api/stock?q=%00воск", None),
    ],
)
async def test_nul_byte_is_rejected_with_text(client, method, url, body):
    resp = await client.request(method.upper(), url, json=body)
    assert "недопустимый символ" in assert_human(resp, 422)


async def test_huge_price_is_validation_error_not_overflow(client, world):
    body = {
        "supplier": "ООО Восковой двор",
        "received_date": date.today().isoformat(),
        "lines": [
            {
                "material_code": "WAX",
                "qty": "1",
                "price": "99999999999999.99",
                "currency": "USD",
                "comment": None,
            }
        ],
    }
    detail = assert_human(await client.post("/api/receipts", json=body), 422)
    assert "цена" in detail


async def test_validation_messages_are_russian(client):
    detail = assert_human(
        await client.post("/api/orders", json={"recipe_id": "abc", "qty": 0, "planned_date": "завтра"}), 422
    )
    assert "рецепт" in detail and "целым числом" in detail
    assert "количество: должно быть больше 0" in detail
    detail = assert_human(
        await client.post("/api/orders", content=b"{not json", headers={"content-type": "application/json"}),
        422,
    )
    assert "JSON" in detail


async def test_database_data_error_is_400_not_500(client):
    """Страховка: если значение, не влезающее в колонку, всё же дошло до PostgreSQL, ответ 400 с текстом."""
    from sqlalchemy import text

    from app.deps import SessionDep

    @app.get("/api/__test_data_error")
    async def overflow(session: SessionDep):
        await session.execute(text("SELECT CAST(:v AS integer)"), {"v": str(TOO_BIG)})

    try:
        detail = assert_human(await client.get("/api/__test_data_error"), 400)
        assert "Некорректное значение" in detail
        assert_human(await client.get("/api/batches?page=100000000000000000"), 422)
    finally:
        app.router.routes = [
            r for r in app.router.routes if getattr(r, "path", "") != "/api/__test_data_error"
        ]
