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
