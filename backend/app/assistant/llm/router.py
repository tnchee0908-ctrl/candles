"""Основная и запасная модель за одним интерфейсом.

Правила:
* 429 / 5xx / таймаут / обрыв соединения ДО первого события → пробуем следующего провайдера;
* ошибка 4xx из-за самого запроса → не повторяем, сразу отдаём ошибку;
* если стрим уже начался (пользователь видел часть ответа) и оборвался → LLMStreamBroken,
  переключаться поздно: запасная модель начала бы ответ заново.
У каждого вызова свой таймаут (asyncio.timeout) поверх таймаута HTTP-клиента.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.assistant.llm.base import (
    LLMError,
    LLMEvent,
    LLMProvider,
    LLMRequest,
    LLMRequestError,
    LLMRetryableError,
    LLMStreamBroken,
)

log = logging.getLogger(__name__)


@dataclass
class RouterStats:
    attempts: list[dict] = field(default_factory=list)


class FallbackLLM:
    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("Нужен хотя бы один провайдер")
        self.providers = providers

    async def stream(self, request: LLMRequest, stats: RouterStats | None = None) -> AsyncIterator[LLMEvent]:
        last_error: LLMError | None = None
        for provider in self.providers:
            started = False
            try:
                async with asyncio.timeout(request.timeout):
                    async for event in provider.stream(request):
                        started = True
                        yield event
                if stats is not None:
                    stats.attempts.append({"model": provider.model, "ok": True})
                return
            except LLMRequestError as exc:
                log.warning("LLM %s: request error, no retry: %s", provider.model, exc)
                if stats is not None:
                    stats.attempts.append({"model": provider.model, "ok": False, "error": "request"})
                raise
            except (LLMRetryableError, TimeoutError) as exc:
                if isinstance(exc, TimeoutError):
                    exc = LLMRetryableError(f"timeout {request.timeout}s")
                if stats is not None:
                    stats.attempts.append({"model": provider.model, "ok": False, "error": str(exc)[:200]})
                if started:
                    log.warning("LLM %s: stream broken after start: %s", provider.model, exc)
                    raise LLMStreamBroken(str(exc)) from exc
                log.warning("LLM %s failed (%s), trying fallback", provider.model, exc)
                last_error = exc
        assert last_error is not None
        raise last_error
