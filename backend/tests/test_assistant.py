"""Ассистент: права через инструменты, подтверждение действий, ПДн, память, остановка, ошибки."""

import asyncio
import csv
import io
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.assistant import memory
from app.assistant.chat import ChatService, build_instructions, confirm_action
from app.assistant.llm.base import LLMRetryableError, TextDelta
from app.assistant.llm.router import FallbackLLM
from app.assistant.pii import Pseudonymizer
from app.errors import DomainError, NotFound
from app.models import Conversation, Message, PendingAction, ProductionOrder
from tests.conftest import add_batch
from tests.fakes import FakeSandbox, ScriptedProvider, call, say

FRIDAY = date.today() + timedelta(days=3)


async def new_conversation(session, user) -> Conversation:
    conv = Conversation(user_id=user.id)
    session.add(conv)
    await session.commit()
    return conv


async def run_turn(chat: ChatService, user, conv, text: str, stop: asyncio.Event | None = None):
    events: list[dict] = []

    async def emit(e):
        events.append(e)

    msg_id = await chat.run_turn(
        user=user, conversation_id=conv.id, text=text, file_ids=[], emit=emit, stop=stop or asyncio.Event()
    )
    return events, msg_id


def tool_outputs(provider: ScriptedProvider) -> list[dict]:
    out = []
    for r in provider.requests:
        for item in r.input:
            if item.get("type") == "function_call_output":
                out.append(json.loads(item["output"]))
    return out


def chat_with(session_factory, steps, sandbox=None) -> tuple[ChatService, ScriptedProvider]:
    provider = ScriptedProvider("fake-primary", steps)
    return ChatService(FallbackLLM([provider]), session_factory, sandbox), provider


# ---------- права и подтверждение ----------


async def test_storekeeper_cannot_plan_through_assistant(session, session_factory, world):
    chat, provider = chat_with(
        session_factory,
        [
            call(
                "propose_production_order",
                {"recipe": "Лаванда", "qty": 200, "planned_date": FRIDAY.isoformat()},
            ),
            say("У вас нет прав на создание заданий."),
        ],
    )
    conv = await new_conversation(session, world.users["sklad"])
    await run_turn(chat, world.users["sklad"], conv, "Запланируй 200 свечей Лаванда на пятницу")

    [output] = tool_outputs(provider)
    assert output.get("forbidden") is True
    assert await session.scalar(select(func.count()).select_from(PendingAction)) == 0
    assert await session.scalar(select(func.count()).select_from(ProductionOrder)) == 0


async def test_cost_is_hidden_from_storekeeper(session, session_factory, world):
    chat, provider = chat_with(
        session_factory, [call("get_order_cost", {"order_number": "З-00001"}), say("Нет прав.")]
    )
    conv = await new_conversation(session, world.users["sklad"])
    await run_turn(chat, world.users["sklad"], conv, "Себестоимость задания З-00001?")
    assert tool_outputs(provider)[0]["forbidden"] is True


async def test_action_changes_data_only_after_confirm(session, session_factory, world):
    await add_batch(session, world, world.wax, "50", days_ago=5)
    await add_batch(session, world, world.wick, "500", days_ago=5)
    chat, provider = chat_with(
        session_factory,
        [
            call(
                "propose_production_order",
                {"recipe": "лаванда", "qty": 40, "planned_date": FRIDAY.isoformat()},
            ),
            say("Подготовил задание, нажмите «Подтвердить»."),
        ],
    )
    tech = world.users["tech"]
    conv = await new_conversation(session, tech)
    events, _ = await run_turn(chat, tech, conv, "Запланируй 40 свечей Лаванда на пятницу")

    action_events = [e for e in events if e["type"] == "action"]
    assert len(action_events) == 1
    assert (
        await session.scalar(select(func.count()).select_from(ProductionOrder)) == 0
    )  # ещё ничего не создано

    action_id = action_events[0]["action"]["id"]
    with pytest.raises(NotFound):  # чужое действие подтвердить нельзя
        await confirm_action(session, world.users["boss"], action_id)
    action = await confirm_action(session, tech, action_id)
    assert action.status == "confirmed"
    order = await session.scalar(select(ProductionOrder))
    assert order is not None and order.qty == 40 and order.status == "planned"
    with pytest.raises(DomainError):  # повторное нажатие не создаёт второе задание
        await confirm_action(session, tech, action_id)
    assert await session.scalar(select(func.count()).select_from(ProductionOrder)) == 1


async def test_tool_arguments_are_validated(session, session_factory, world):
    chat, provider = chat_with(
        session_factory,
        [
            call(
                "propose_production_order",
                {"recipe": "Лаванда", "qty": -5, "planned_date": "завтра", "drop_table": True},
            ),
            say("Не получилось."),
        ],
    )
    conv = await new_conversation(session, world.users["tech"])
    await run_turn(chat, world.users["tech"], conv, "сделай -5 свечей")
    output = tool_outputs(provider)[0]
    assert output["error"] == "Некорректные аргументы инструмента"
    assert await session.scalar(select(func.count()).select_from(PendingAction)) == 0


# ---------- ПДн ----------


async def test_pii_is_masked_for_llm_and_restored_for_user(session, session_factory, world):
    await add_batch(session, world, world.wax, "10", days_ago=2, comment="Принял Петров И. С.")
    pii = await Pseudonymizer.load(session)
    supplier_alias = pii.alias_for("supplier", world.supplier.id)
    person_alias = pii.alias_for("person", world.users["sklad"].id)

    chat, provider = chat_with(
        session_factory,
        [
            call("find_batches", {"supplier": supplier_alias}),
            say(f"Партию от {supplier_alias} принял {person_alias}."),
        ],
    )
    boss = world.users["boss"]
    conv = await new_conversation(session, boss)
    events, msg_id = await run_turn(
        chat, boss, conv, "Что привёз Восковой двор, ООО? Это принимал Петрову И.?"
    )

    sent = provider.sent_text()
    for real in ("Восков", "Петров", "Кузнецов"):
        assert real not in sent, f"{real} утекло в LLM"
    assert supplier_alias in sent and person_alias in sent
    # Поиск по псевдониму реально нашёл партию — аргумент был размаскирован перед вызовом сервиса.
    assert tool_outputs(provider)[0]["total"] == 1

    msg = await session.get(Message, msg_id)
    assert msg.content == "Партию от ООО Восковой двор принял Петров Иван Сергеевич."
    streamed = "".join(e["text"] for e in events if e["type"] == "delta")
    assert streamed == msg.content


async def test_export_for_code_interpreter_has_no_pii(session, session_factory, world):
    await add_batch(session, world, world.wax, "10", days_ago=2)
    sandbox = FakeSandbox()
    chat, provider = chat_with(
        session_factory, [call("export_dataset", {"dataset": "batches"}), say("Готово.")], sandbox
    )
    conv = await new_conversation(session, world.users["boss"])
    await run_turn(chat, world.users["boss"], conv, "выгрузи партии")
    [content] = sandbox.files.values()
    rows = list(csv.DictReader(io.StringIO(content.decode())))
    assert rows and rows[0]["supplier"].startswith("SUPPLIER_")
    assert "Восков" not in content.decode()


# ---------- память ----------


async def test_memory_is_isolated_between_users(session, session_factory, world):
    tech, tech2 = world.users["tech"], world.users["tech2"]
    chat, provider = chat_with(
        session_factory,
        [
            call("remember_fact", {"fact": "Считать себестоимость в евро"}),
            say("Запомнил."),
            say("Здравствуйте!"),
        ],
    )
    conv1 = await new_conversation(session, tech)
    await run_turn(chat, tech, conv1, "Всегда считай мне в евро")
    assert [f.text for f in await memory.list_facts(session, tech.id)] == ["Считать себестоимость в евро"]

    conv2 = await new_conversation(session, tech2)
    await run_turn(chat, tech2, conv2, "Привет")
    assert (
        "Считать себестоимость в евро" not in provider.requests[-1].instructions
    )  # чужой факт не попал в промпт

    pii = await Pseudonymizer.load(session)
    own = build_instructions(world.actors["tech"], "PERSON_2", ["Считать себестоимость в евро"], pii, False)
    assert "Считать себестоимость в евро" in own

    fact_id = (await memory.list_facts(session, tech.id))[0].id
    with pytest.raises(NotFound):
        await memory.delete_fact(session, tech2.id, fact_id)
    await memory.delete_fact(session, tech.id, fact_id)
    assert await memory.list_facts(session, tech.id) == []


# ---------- стрим и ошибки ----------


async def test_stop_saves_partial_answer(session, session_factory, world):
    class Slow(ScriptedProvider):
        async def stream(self, request):
            self.requests.append(request)
            yield TextDelta("Первая часть ответа")
            await asyncio.sleep(30)
            yield TextDelta(" — не дойдёт")

    chat = ChatService(FallbackLLM([Slow("slow", [])]), session_factory)
    conv = await new_conversation(session, world.users["tech"])
    stop = asyncio.Event()

    async def press_stop():
        await asyncio.sleep(0.3)
        stop.set()

    _, (events, msg_id) = await asyncio.gather(
        press_stop(), run_turn(chat, world.users["tech"], conv, "?", stop)
    )
    msg = await session.get(Message, msg_id)
    assert msg.status == "interrupted"
    assert msg.content == "Первая часть ответа"
    assert events[-1]["type"] == "done"


async def test_llm_outage_gives_friendly_message(session, session_factory, world):
    llm = FallbackLLM(
        [ScriptedProvider("a", [LLMRetryableError("503")]), ScriptedProvider("b", [LLMRetryableError("503")])]
    )
    chat = ChatService(llm, session_factory)
    conv = await new_conversation(session, world.users["tech"])
    events, msg_id = await run_turn(chat, world.users["tech"], conv, "?")
    msg = await session.get(Message, msg_id)
    assert msg.status == "error"
    assert "временно недоступна" in msg.meta["error"]


async def test_fallback_model_is_recorded(session, session_factory, world):
    primary = ScriptedProvider("primary", [LLMRetryableError("429")])
    backup = ScriptedProvider("backup", [say("Ответ", model="backup-model")])
    chat = ChatService(FallbackLLM([primary, backup]), session_factory)
    conv = await new_conversation(session, world.users["tech"])
    events, msg_id = await run_turn(chat, world.users["tech"], conv, "?")
    msg = await session.get(Message, msg_id)
    assert msg.model == "backup-model"
    assert [a["ok"] for a in msg.meta["llm_attempts"]] == [False, True]
