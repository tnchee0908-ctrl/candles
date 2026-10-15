"""Провайдер-независимый интерфейс LLM.

Оркестратор чата работает только с этими типами. Чтобы добавить другого провайдера (Anthropic,
локальную модель), достаточно реализовать LLMProvider.stream() и сконвертировать его события сюда.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class LLMRequest:
    instructions: str
    # История в формате элементов Responses API: {"role": "user"|"assistant", "content": str},
    # {"type": "function_call", ...}, {"type": "function_call_output", ...}, {"type": "item_reference", ...}
    input: list[dict[str, Any]]
    tools: list[ToolSpec] = field(default_factory=list)
    # id контейнера Code Interpreter; None — встроенный инструмент выключен.
    code_container: str | None = None
    timeout: float = 60.0


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: str  # JSON-строка от модели — внешний ввод, валидируется перед использованием


@dataclass
class CodeRun:
    code: str
    logs: str = ""
    error: bool = False


@dataclass
class Completed:
    model: str
    # Элементы ответа, которые нужно дописать в input для следующего шага (function_call и т.п.).
    output_items: list[dict[str, Any]]
    usage: dict[str, Any] = field(default_factory=dict)


LLMEvent = TextDelta | ToolCall | CodeRun | Completed


class LLMError(Exception):
    """Базовая ошибка LLM. user_message — что показать пользователю."""

    user_message = "Модель временно недоступна. Попробуйте ещё раз чуть позже."


class LLMRetryableError(LLMError):
    """429, 5xx, таймаут, обрыв соединения — имеет смысл попробовать запасную модель."""


class LLMRequestError(LLMError):
    """4xx из-за самого запроса (плохие параметры, слишком длинный контекст) — повтор не поможет."""

    user_message = "Запрос к модели отклонён. Попробуйте переформулировать вопрос или начать новый диалог."


class LLMStreamBroken(LLMError):
    """Ответ оборвался посреди стрима — часть текста уже показана, переключаться поздно."""

    user_message = "Ответ модели оборвался. Сохранена часть ответа."


class LLMProvider(Protocol):
    name: str
    model: str

    def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]: ...
