"""Граница API: некорректный ввод → понятный текст по-русски, никогда не 500."""

import re
from decimal import Decimal

import httpx
import pytest

from app.db import get_session
from app.main import app
from app.services.auth import create_token
from app.services.common import today

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
        "received_date": today().isoformat(),
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


async def test_token_signed_with_example_secret_is_rejected(client, world):
    """Токен руководителя, подписанный секретом из .env.example, не принимается."""
    from datetime import UTC, datetime, timedelta

    import jwt

    forged = jwt.encode(
        {"sub": str(world.users["boss"].id), "exp": datetime.now(UTC) + timedelta(hours=1)},
        "change-me-in-production",
        algorithm="HS256",
    )
    resp = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401
    assert (await client.get("/api/auth/me")).status_code == 200  # настоящий токен работает


async def test_login_bruteforce_is_limited(client, world):
    for _ in range(5):
        assert_human(await client.post("/api/auth/login", json={"username": "boss", "password": "нет"}), 400)
    detail = assert_human(
        await client.post("/api/auth/login", json={"username": "boss", "password": "x"}), 429
    )
    assert "Слишком много неудачных попыток" in detail
    # С другого адреса тот же логин входит — один человек не может заблокировать вход другим.
    ok = await client.post(
        "/api/auth/login", json={"username": "boss", "password": "x"}, headers={"X-Forwarded-For": "10.0.0.7"}
    )
    assert ok.status_code == 200


@pytest.mark.parametrize(
    "body_patch,expected",
    [
        ({"received_date": "0001-01-01"}, "дата поступления: должно быть не меньше 01.01.2000"),
        ({"received_date": "9999-12-31"}, "дата поступления: должно быть не больше 31.12.2100"),
    ],
)
async def test_absurd_receipt_dates_are_rejected(client, body_patch, expected):
    body = {
        "supplier": "ООО Восковой двор",
        "received_date": today().isoformat(),
        "lines": [{"material_code": "WAX", "qty": "1", "price": "10", "currency": "RUB"}],
    } | body_patch
    assert expected in assert_human(await client.post("/api/receipts", json=body), 422)


async def test_far_dates_are_business_errors(client, world, session):
    from datetime import timedelta

    from app.services import batches
    from app.services.batches import ReceiptLine

    resp = await client.post(
        "/api/orders",
        json={
            "recipe_id": world.recipe.id,
            "qty": 1,
            "planned_date": (today() + timedelta(days=800)).isoformat(),
        },
    )
    assert "не больше чем на 2 года" in assert_human(resp, 400)
    with pytest.raises(Exception, match="слишком давняя"):
        await batches.create_receipt(
            session,
            world.actors["sklad"],
            supplier_name="ООО Восковой двор",
            received_date=today() - timedelta(days=6 * 366),
            lines=[ReceiptLine("WAX", Decimal("1"), Decimal("1"), "RUB")],
        )
    for q in ("date_from=0001-01-01&date_to=2026-01-01", "date_from=2026-01-01&date_to=9999-12-31"):
        assert_human(await client.get(f"/api/orders/shortages?{q}"), 422)


async def test_unreadable_body_is_russian(client):
    """Тело не в UTF-8 (так шлёт, например, консоль Windows) — понятный текст, а не «error parsing the body»."""
    resp = await client.post(
        "/api/chat/memory", content="привет".encode("cp1251"), headers={"content-type": "application/json"}
    )
    assert resp.status_code in (400, 422)
    assert_human(resp, resp.status_code)
