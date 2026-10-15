"""OpenAI Responses API со стримингом. Тонкий собственный слой, без агентных фреймворков."""

from collections.abc import AsyncIterator
from typing import Any

import httpx
import openai
from openai import NOT_GIVEN, AsyncOpenAI

from app.assistant.llm.base import (
    CodeRun,
    Completed,
    LLMEvent,
    LLMRequest,
    LLMRequestError,
    LLMRetryableError,
    TextDelta,
    ToolCall,
)


def make_client(api_key: str) -> AsyncOpenAI:
    # max_retries=0: повторы и переход на запасную модель делает наш роутер, а не SDK.
    return AsyncOpenAI(api_key=api_key or "missing", max_retries=0)


class OpenAIProvider:
    name = "openai"

    def __init__(self, client: AsyncOpenAI, model: str):
        self.client = client
        self.model = model

    def _tools(self, request: LLMRequest) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "strict": False,
            }
            for t in request.tools
        ]
        if request.code_container:
            tools.append({"type": "code_interpreter", "container": request.code_container})
        return tools

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]:
        try:
            stream = await self.client.responses.create(
                model=self.model,
                instructions=request.instructions,
                input=request.input,  # type: ignore[arg-type]
                tools=self._tools(request),  # type: ignore[arg-type]
                include=["code_interpreter_call.outputs"],
                temperature=request.temperature if request.temperature is not None else NOT_GIVEN,
                stream=True,
                store=True,  # нужно, чтобы ссылаться на элементы ответа (item_reference) на следующем шаге
                timeout=httpx.Timeout(request.timeout, connect=10.0),
            )
            async for event in stream:
                etype = event.type
                if etype == "response.output_text.delta":
                    yield TextDelta(event.delta)
                elif etype == "response.output_item.done":
                    item = event.item
                    if item.type == "function_call":
                        yield ToolCall(call_id=item.call_id, name=item.name, arguments=item.arguments or "{}")
                    elif item.type == "code_interpreter_call":
                        logs = "\n".join(
                            getattr(o, "logs", "") or ""
                            for o in (item.outputs or [])
                            if getattr(o, "type", "") == "logs"
                        )
                        yield CodeRun(code=item.code or "", logs=logs, error=item.status == "failed")
                elif etype == "response.completed":
                    resp = event.response
                    usage = resp.usage.model_dump() if resp.usage else {}
                    yield Completed(model=resp.model, output_items=_to_input_items(resp.output), usage=usage)
                elif etype in ("response.failed", "response.incomplete"):
                    err = getattr(event.response, "error", None)
                    raise LLMRetryableError(f"{etype}: {getattr(err, 'message', '')}")
                elif etype == "error":
                    raise LLMRetryableError(f"stream error: {getattr(event, 'message', '')}")
        except (openai.APITimeoutError, openai.APIConnectionError) as exc:
            raise LLMRetryableError(f"{type(exc).__name__}") from exc
        except openai.RateLimitError as exc:
            raise LLMRetryableError("429 rate limit") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMRetryableError(f"HTTP {exc.status_code}") from exc
            raise LLMRequestError(f"HTTP {exc.status_code}: {exc.message[:300]}") from exc


def _to_input_items(output: list[Any]) -> list[dict[str, Any]]:
    """Элементы ответа → элементы input следующего запроса.

    function_call передаём целиком (к нему цепляется function_call_output), текст — как сообщение
    ассистента, остальное (reasoning, code_interpreter_call) — ссылкой на сохранённый элемент.
    """
    items: list[dict[str, Any]] = []
    for item in output:
        if item.type == "function_call":
            items.append(
                {
                    "type": "function_call",
                    "call_id": item.call_id,
                    "name": item.name,
                    "arguments": item.arguments,
                }
            )
        elif item.type == "message":
            text = "".join(getattr(c, "text", "") or "" for c in item.content)
            if text:
                items.append({"role": "assistant", "content": text})
        elif getattr(item, "id", None):
            items.append({"type": "item_reference", "id": item.id})
    return items
