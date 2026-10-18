"""Переход на запасную модель: 429/5xx/таймаут — да, 4xx — нет, обрыв после начала — нет."""

import asyncio

import pytest

from app.assistant.llm.base import (
    LLMRequest,
    LLMRequestError,
    LLMRetryableError,
    LLMStreamBroken,
    TextDelta,
)
from app.assistant.llm.router import FallbackLLM, RouterStats
from tests.fakes import ScriptedProvider, say

REQ = LLMRequest(instructions="i", input=[{"role": "user", "content": "привет"}], timeout=1)


async def collect(llm: FallbackLLM, stats: RouterStats | None = None, req: LLMRequest = REQ) -> str:
    return "".join([e.text async for e in llm.stream(req, stats) if isinstance(e, TextDelta)])


@pytest.mark.parametrize("error", [LLMRetryableError("429 rate limit"), LLMRetryableError("HTTP 503")])
async def test_fallback_on_retryable_errors(error):
    primary = ScriptedProvider("primary", [error])
    backup = ScriptedProvider("backup", [say("ответ запасной")])
    stats = RouterStats()
    assert await collect(FallbackLLM([primary, backup]), stats) == "ответ запасной"
    assert [a["model"] for a in stats.attempts] == ["primary", "backup"]
    assert stats.attempts[0]["ok"] is False


async def test_fallback_on_timeout():
    class Hanging(ScriptedProvider):
        async def stream(self, request):
            self.requests.append(request)
            await asyncio.sleep(10)
            yield TextDelta("никогда")

    backup = ScriptedProvider("backup", [say("успел")])
    assert await collect(FallbackLLM([Hanging("primary", []), backup])) == "успел"


async def test_request_error_is_not_retried():
    primary = ScriptedProvider("primary", [LLMRequestError("HTTP 400")])
    backup = ScriptedProvider("backup", [say("не должен быть вызван")])
    with pytest.raises(LLMRequestError):
        await collect(FallbackLLM([primary, backup]))
    assert backup.requests == []


async def test_broken_stream_after_start_is_not_restarted():
    primary = ScriptedProvider("primary", [[TextDelta("Начал отвечать"), LLMRetryableError("conn reset")]])
    backup = ScriptedProvider("backup", [say("заново")])
    with pytest.raises(LLMStreamBroken):
        await collect(FallbackLLM([primary, backup]))
    assert backup.requests == []


async def test_all_providers_down():
    llm = FallbackLLM(
        [ScriptedProvider("a", [LLMRetryableError("500")]), ScriptedProvider("b", [LLMRetryableError("500")])]
    )
    with pytest.raises(LLMRetryableError):
        await collect(llm)


async def test_invalid_key_is_reported_clearly_and_not_retried():
    from app.assistant.llm.base import LLMAuthError

    primary = ScriptedProvider("primary", [LLMAuthError("HTTP 401")])
    backup = ScriptedProvider("backup", [say("не должен быть вызван")])
    with pytest.raises(LLMAuthError) as exc:
        await collect(FallbackLLM([primary, backup]))
    assert backup.requests == []
    assert "Ключ OpenAI недействителен" in exc.value.user_message


async def test_region_block_from_openai_is_explained():
    """Ответ OpenAI 403 unsupported_country_region_territory превращается в понятную ошибку."""
    import httpx
    import openai

    from app.assistant.llm.base import LLMRegionError, LLMRequest
    from app.assistant.llm.openai_provider import OpenAIProvider

    class Responses:
        async def create(self, **kwargs):
            request = httpx.Request("POST", "https://api.openai.com/v1/responses")
            body = {
                "error": {
                    "code": "unsupported_country_region_territory",
                    "message": "Country, region, or territory not supported",
                }
            }
            response = httpx.Response(403, request=request, json=body)
            raise openai.PermissionDeniedError(
                "Country, region, or territory not supported", response=response, body=body["error"]
            )

    class Client:
        responses = Responses()

    provider = OpenAIProvider(Client(), "gpt-test")  # type: ignore[arg-type]
    with pytest.raises(LLMRegionError) as exc:
        async for _ in provider.stream(LLMRequest(instructions="i", input=[])):
            pass
    assert "страну" in exc.value.user_message


def _openai_error(status: int, code: str, message: str):
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    body = {"error": {"code": code, "message": message}}
    response = httpx.Response(status, request=request, json=body)
    cls = {400: openai.BadRequestError, 403: openai.PermissionDeniedError, 404: openai.NotFoundError}[status]
    return cls(message, response=response, body=body["error"])


def _broken_openai(error):
    from app.assistant.llm.openai_provider import OpenAIProvider

    class Responses:
        async def create(self, **kwargs):
            raise error

    class Client:
        responses = Responses()

    return OpenAIProvider(Client(), "gpt-4.1-mini-broken")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "status,code,message",
    [
        (404, "model_not_found", "The model `gpt-4.1-mini-broken` does not exist"),
        (403, "model_not_found", "Project does not have access to model gpt-x"),
        (
            400,
            "unsupported_parameter",
            "Unsupported parameter: 'temperature' is not supported with this model.",
        ),
    ],
)
async def test_broken_primary_model_switches_to_fallback(status, code, message):
    """Испортили имя основной модели в .env — отвечает запасная, а не «переформулируйте вопрос»."""
    backup = ScriptedProvider("gpt-4o-mini", [say("ответ запасной")])
    stats = RouterStats()
    llm = FallbackLLM([_broken_openai(_openai_error(status, code, message)), backup])
    assert await collect(llm, stats) == "ответ запасной"
    assert [(a["model"], a["ok"], a["fallback"]) for a in stats.attempts] == [
        ("gpt-4.1-mini-broken", False, False),
        ("gpt-4o-mini", True, True),
    ]


async def test_real_request_error_is_still_not_retried():
    error = _openai_error(400, "context_length_exceeded", "This model's maximum context length is exceeded")
    backup = ScriptedProvider("backup", [say("не должен быть вызван")])
    with pytest.raises(LLMRequestError):
        await collect(FallbackLLM([_broken_openai(error), backup]))
    assert backup.requests == []


async def test_stream_error_before_first_token_switches_to_fallback():
    """Ошибка внутри уже открытого стрима, но до первого текста: пользователь ничего не видел — переключаемся."""
    from app.assistant.llm.base import Heartbeat

    primary = ScriptedProvider("primary", [[Heartbeat(), Heartbeat(), LLMRetryableError("stream error")]])
    backup = ScriptedProvider("backup", [say("запасная ответила")])
    stats = RouterStats()
    assert await collect(FallbackLLM([primary, backup]), stats) == "запасная ответила"
    assert stats.attempts[0]["ok"] is False and stats.attempts[1]["ok"] is True


async def test_long_code_run_with_progress_events_is_not_cut():
    """Шаг идёт дольше таймаута простоя, но модель присылает события прогресса — не обрываем."""
    from app.assistant.llm.base import Heartbeat

    class LongCode(ScriptedProvider):
        async def stream(self, request):
            self.requests.append(request)
            for _ in range(6):
                await asyncio.sleep(0.1)
                yield Heartbeat()
            yield TextDelta("посчитал")

    req = LLMRequest(instructions="i", input=[], timeout=5, idle_timeout=0.3)
    backup = ScriptedProvider("backup", [say("не нужен")])
    assert await collect(FallbackLLM([LongCode("primary", []), backup]), req=req) == "посчитал"
    assert backup.requests == []


async def test_silent_stream_hits_idle_timeout():
    class Silent(ScriptedProvider):
        async def stream(self, request):
            self.requests.append(request)
            await asyncio.sleep(5)
            yield TextDelta("никогда")

    req = LLMRequest(instructions="i", input=[], timeout=10, idle_timeout=0.2)
    backup = ScriptedProvider("backup", [say("успел")])
    assert await collect(FallbackLLM([Silent("primary", []), backup]), req=req) == "успел"


async def test_api_error_inside_stream_switches_to_fallback():
    """openai.APIError без HTTP-статуса из уже открытого потока — сбой сервиса: до первого токена → запасная."""
    import httpx
    import openai

    from app.assistant.llm.openai_provider import OpenAIProvider

    async def broken_stream():
        raise openai.APIError("stream died", request=httpx.Request("POST", "https://x"), body=None)
        yield  # noqa: B901

    class Responses:
        async def create(self, **kwargs):
            return broken_stream()

    class Client:
        responses = Responses()

    backup = ScriptedProvider("backup", [say("запасная")])
    assert await collect(FallbackLLM([OpenAIProvider(Client(), "primary"), backup])) == "запасная"  # type: ignore[arg-type]


def test_sql_errors_do_not_carry_parameter_values():
    from app.db import engine

    assert engine.sync_engine.hide_parameters is True
