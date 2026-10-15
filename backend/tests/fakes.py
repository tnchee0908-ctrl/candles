"""Заглушки LLM и песочницы для тестов: сценарий ответов задаётся списком, запросы записываются."""

import json
from itertools import count
from typing import Any

from app.assistant.llm.base import Completed, LLMEvent, LLMRequest, TextDelta, ToolCall
from app.assistant.sandbox import SandboxFile

_ids = count(1)


def say(text: str, model: str = "fake-primary") -> list[LLMEvent]:
    """Шаг, на котором модель просто отвечает текстом (по кускам, как в стриме)."""
    chunks = [text[i : i + 7] for i in range(0, len(text), 7)]
    return [
        *(TextDelta(c) for c in chunks),
        Completed(model=model, output_items=[{"role": "assistant", "content": text}]),
    ]


def call(name: str, args: dict[str, Any], model: str = "fake-primary") -> list[LLMEvent]:
    """Шаг, на котором модель вызывает инструмент."""
    call_id = f"call_{next(_ids)}"
    raw = json.dumps(args, ensure_ascii=False)
    return [
        ToolCall(call_id=call_id, name=name, arguments=raw),
        Completed(
            model=model,
            output_items=[{"type": "function_call", "call_id": call_id, "name": name, "arguments": raw}],
        ),
    ]


class ScriptedProvider:
    name = "fake"

    def __init__(self, model: str, steps: list[list[LLMEvent] | Exception]):
        self.model = model
        self.steps = list(steps)
        self.requests: list[LLMRequest] = []

    async def stream(self, request: LLMRequest):
        self.requests.append(request)
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        for event in step:
            if isinstance(event, Exception):
                raise event
            yield event

    def sent_text(self) -> str:
        """Всё, что ушло в модель: инструкции + история + результаты инструментов."""
        return "\n".join(
            r.instructions + "\n" + json.dumps(r.input, ensure_ascii=False) for r in self.requests
        )


class FakeSandbox:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    async def ensure(self, container_id, name):
        return container_id or "cntr_test", container_id is None

    async def upload(self, container_id, filename, data):
        path = f"/mnt/data/{filename}"
        self.files[path] = data
        return path

    async def list_files(self, container_id):
        return [SandboxFile(id=p, path=p, source="user", size=len(d)) for p, d in self.files.items()]

    async def download(self, container_id, file_id):
        return self.files[file_id]
