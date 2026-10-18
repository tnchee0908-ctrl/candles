"""Основная и запасная модель за одним интерфейсом.

Правила:
* 429 / 5xx / таймаут / обрыв соединения ДО первого события → пробуем следующего провайдера;
* модель недоступна (404 model_not_found, нет доступа, неподдерживаемый параметр) → тоже следующий:
  переформулировка вопроса тут не поможет, а другая модель ответит;
* ошибка 4xx из-за самого запроса → не повторяем, сразу отдаём ошибку;
* если стрим уже начался (пользователь видел часть ответа) и оборвался → LLMStreamBroken,
  переключаться поздно: запасная модель начала бы ответ заново.

Таймауты: request.idle_timeout — сколько ждём следующего события стрима (служебные события прогресса
тоже считаются: долгий расчёт в Code Interpreter не обрывается, пока модель жива); request.timeout —
потолок на весь шаг.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.assistant.llm.base import (
    Heartbeat,
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
    # {"model", "ok", "fallback": это не основная модель, "error"?} — по одной записи на попытку.
    attempts: list[dict] = field(default_factory=list)


class FallbackLLM:
    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("Нужен хотя бы один провайдер")
        self.providers = providers

    async def stream(self, request: LLMRequest, stats: RouterStats | None = None) -> AsyncIterator[LLMEvent]:
        last_error: LLMError | None = None
        for index, provider in enumerate(self.providers):
            started = False
            record = {"model": provider.model, "fallback": index > 0}
            try:
                async with asyncio.timeout(request.timeout):
                    events = aiter(provider.stream(request))
                    while True:
                        try:
                            event = await asyncio.wait_for(anext(events), request.idle_timeout)
                        except StopAsyncIteration:
                            break
                        if isinstance(event, Heartbeat):
                            continue
                        started = True
                        yield event
                if stats is not None:
                    stats.attempts.append(record | {"ok": True})
                return
            except LLMRequestError as exc:
                log.warning("LLM %s: request error, no retry: %s", provider.model, exc)
                if stats is not None:
                    stats.attempts.append(record | {"ok": False, "error": "request"})
                raise
            except (LLMRetryableError, TimeoutError) as exc:
                if isinstance(exc, TimeoutError):
                    exc = LLMRetryableError(
                        f"timeout (idle {request.idle_timeout}s / step {request.timeout}s)"
                    )
                if stats is not None:
                    stats.attempts.append(record | {"ok": False, "error": str(exc)[:200]})
                if started:
                    log.warning("LLM %s: stream broken after start: %s", provider.model, exc)
                    raise LLMStreamBroken(str(exc)) from exc
                log.warning("LLM %s failed (%s), trying fallback", provider.model, exc)
                last_error = exc
        assert last_error is not None
        raise last_error
