"""Фаззинг всех эндпоинтов из OpenAPI: ни одного 500, ответ — JSON, текст ошибки по-русски.

Запуск (стенд поднят):  docker compose run --rm tests python scripts/fuzz_api.py [http://backend:8000]
Для каждой операции перебираются: без токена, мусорный токен, три роли; плохие значения в адресе,
параметрах и теле (пустые, огромные, NUL, отрицательные, экстремальные даты и числа, не тот тип).
Отправку сообщения ассистенту с корректным телом не делает — это вызвало бы настоящую модель.
"""

import asyncio
import json
import re
import sys
from collections import Counter

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://backend:8000"
USERS = {"sklad": "sklad123", "tech": "tech123", "boss": "boss123"}
ENGLISH = re.compile(
    r"Input should|Field required|Not Found|Method Not Allowed|value is not|Internal Server Error|"
    r"Value error|validation error|Unprocessable|Traceback",
    re.I,
)
BAD_IDS = ["0", "-1", "2147483648", "99999999999999999999", "abc", "1.5", "%00", "%20"]
BAD_SCALARS = [
    "",
    "x" * 5000,
    "\u0000",
    "-1",
    "0",
    "1e309",
    "NaN",
    "Infinity",
    "9999-12-31",
    "0001-01-01",
    "2026-02-30",
    "' OR 1=1 --",
    "<script>alert(1)</script>",
    "../../etc/passwd",
]
BAD_JSON_VALUES = [
    None,
    "",
    "\u0000",
    "x" * 100_000,
    -1,
    0,
    2**31,
    10**30,
    1e308,
    -1e308,
    "NaN",
    "9999-12-31",
    "0001-01-01",
    [],
    {},
    True,
]


def sample(schema: dict, components: dict, depth: int = 0) -> object:
    """Правдоподобное значение по схеме (база для мутаций одного поля)."""
    if "$ref" in schema:
        schema = components[schema["$ref"].rsplit("/", 1)[-1]]
    if "anyOf" in schema:
        schema = next((s for s in schema["anyOf"] if s.get("type") != "null"), schema["anyOf"][0])
    t = schema.get("type")
    if "enum" in schema:
        return schema["enum"][0]
    if "const" in schema:
        return schema["const"]
    if t == "object" or "properties" in schema:
        if depth > 3:
            return {}
        return {k: sample(v, components, depth + 1) for k, v in (schema.get("properties") or {}).items()}
    if t == "array":
        return [sample(schema.get("items") or {}, components, depth + 1)]
    if t == "integer":
        return 1
    if t == "number":
        return 1
    if t == "boolean":
        return False
    if schema.get("format") == "date":
        return "2026-10-16"
    return "Воск"


def body_variants(base: object) -> list[object]:
    out: list[object] = [None, [], "строка", {"unknown": 1}, {}]
    if isinstance(base, dict):
        for key in base:
            for bad in BAD_JSON_VALUES:
                mutated = dict(base)
                mutated[key] = bad
                out.append(mutated)
            if isinstance(base[key], list) and base[key] and isinstance(base[key][0], dict):
                for sub in base[key][0]:
                    for bad in BAD_JSON_VALUES:
                        item = dict(base[key][0])
                        item[sub] = bad
                        mutated = dict(base)
                        mutated[key] = [item]
                        out.append(mutated)
    return out


async def tokens(client: httpx.AsyncClient) -> dict[str, dict]:
    headers = {"none": {}, "garbage": {"Authorization": "Bearer not.a.jwt"}}
    for user, password in USERS.items():
        resp = await client.post("/api/auth/login", json={"username": user, "password": password})
        resp.raise_for_status()
        headers[user] = {"Authorization": f"Bearer {resp.json()['token']}"}
    return headers


def check(resp: httpx.Response, label: str, problems: list[str]) -> None:
    if resp.status_code >= 500:
        problems.append(f"{resp.status_code} {label}: {resp.text[:200]}")
        return
    if resp.headers.get("content-type", "").startswith("text/event-stream"):
        return
    try:
        data = resp.json()
    except ValueError:
        problems.append(f"не JSON {resp.status_code} {label}: {resp.text[:120]}")
        return
    if resp.status_code >= 400:
        detail = data.get("detail") if isinstance(data, dict) else None
        if not isinstance(detail, str) or ENGLISH.search(detail):
            problems.append(f"текст ошибки {resp.status_code} {label}: {str(data)[:200]}")


async def main() -> int:
    problems: list[str] = []
    statuses: Counter = Counter()
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        spec = (await client.get("/openapi.json")).json()
        components = spec.get("components", {}).get("schemas", {})
        auth = await tokens(client)
        sent = 0
        for path, ops in spec["paths"].items():
            for method, op in ops.items():
                params = op.get("parameters", [])
                path_params = [p["name"] for p in params if p["in"] == "path"]
                query_params = [p for p in params if p["in"] == "query"]
                body_schema = (
                    op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
                )
                is_chat_send = path.endswith("/messages") and method == "post"
                requests: list[tuple[str, dict | None, object]] = []
                # 1) плохие id в адресе
                for bad in BAD_IDS if path_params else ["1"]:
                    url = path
                    for name in path_params:
                        url = url.replace("{" + name + "}", bad)
                    requests.append(
                        (
                            url,
                            None,
                            sample(body_schema, components) if body_schema and not is_chat_send else None,
                        )
                    )
                url_ok = path
                for name in path_params:
                    url_ok = url_ok.replace("{" + name + "}", "1")
                # 2) плохие значения параметров запроса
                for q in query_params:
                    for bad in BAD_SCALARS:
                        requests.append((url_ok, {q["name"]: bad}, None))
                # 3) плохие тела
                if body_schema:
                    base = sample(body_schema, components)
                    for variant in body_variants(base):
                        if is_chat_send and variant == base:
                            continue
                        requests.append((url_ok, None, variant))
                for who, headers in auth.items():
                    for url, query, body in requests:
                        if (
                            is_chat_send
                            and isinstance(body, dict)
                            and isinstance(body.get("text"), str)
                            and 0 < len(body["text"]) <= 4000
                            and "\u0000" not in body["text"]
                        ):
                            continue  # корректный вопрос ушёл бы в настоящую модель
                        kwargs: dict = {"headers": headers, "params": query}
                        if body is not None or method in ("post", "put", "patch"):
                            kwargs["content"] = json.dumps(body, ensure_ascii=False)
                            kwargs["headers"] = headers | {"content-type": "application/json"}
                        if isinstance(body, str) and body == "строка" and method in ("post", "put", "patch"):
                            kwargs["content"] = "тело не в UTF-8".encode("cp1251")  # нечитаемое тело
                        try:
                            resp = await client.request(method.upper(), url, **kwargs)
                        except httpx.HTTPError as exc:
                            problems.append(f"сеть {method.upper()} {url}: {type(exc).__name__}")
                            continue
                        sent += 1
                        statuses[resp.status_code] += 1
                        check(
                            resp, f"[{who}] {method.upper()} {url} q={query} body={str(body)[:80]}", problems
                        )
    print(f"запросов: {sent}; статусы: {dict(sorted(statuses.items()))}")
    for p in problems[:60]:
        print("  ✗", p)
    print(f"проблем: {len(problems)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
