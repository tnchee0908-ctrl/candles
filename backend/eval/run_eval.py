"""Прогон эталонных вопросов через настоящего ассистента (нужен OPENAI_API_KEY) с отчётом.

Запуск (в контейнере):  docker compose exec backend python -m eval.run_eval
Параметры: --only id1,id2   --no-judge   --keep (не удалять созданные диалоги)

Машинные проверки и оценка LLM-судьёй считаются и выводятся раздельно. Запускается вручную перед релизом.
"""

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import delete, select

from app.assistant.chat import load_prompt
from app.assistant.factory import get_chat_service
from app.assistant.llm.openai_provider import make_client
from app.assistant.tools import _avg_unit_cost
from app.config import get_settings
from app.db import SessionLocal
from app.models import Batch, Conversation, Material, Message, ProductionOrder, User, UserFact
from app.services import reports
from app.services.common import Actor, q_money

HERE = Path(__file__).resolve().parent
REPORTS = HERE / "reports"


@dataclass
class Result:
    qid: str
    user: str
    question: str
    answer: str = ""
    status: str = ""
    model: str | None = None
    tools: list[str] = field(default_factory=list)
    code_runs: int = 0
    files: list[str] = field(default_factory=list)
    actions: int = 0
    checks: dict[str, bool] = field(default_factory=dict)
    judge: dict[str, Any] | None = None
    seconds: float = 0.0
    error: str | None = None

    @property
    def machine_ok(self) -> bool:
        return all(self.checks.values())


# ---------- эталонные значения из БД ----------


async def compute_truth(session) -> dict[str, Any]:
    boss = await session.scalar(select(User).where(User.username == "boss"))
    actor = Actor(boss.id, boss.full_name, boss.role)
    truth: dict[str, Any] = {}

    soy = await reports.material_stock(session, actor, "WAX-SOY")
    truth["free_soy"] = soy[0]["free"]

    today = date.today()
    ws, we = reports.week_bounds(today)
    shortage = await reports.shortages_for_period(session, actor, ws, we)
    coc = next((r for r in shortage["by_material"] if r["material_code"] == "WAX-COC"), None)
    truth["coc_shortage_week"] = coc["shortage"] if coc else Decimal(0)

    batches = list(await session.scalars(select(Batch).order_by(Batch.id)))
    weekend = next(b for b in batches if b.received_date.weekday() >= 5 and b.currency != "RUB")
    truth["weekend_batch"] = weekend.number
    truth["weekend_batch_rate"] = weekend.rate
    truth["injection_batch"] = next(
        b.number for b in batches if b.comment and "игнорируй" in b.comment.lower()
    )

    last = await session.scalar(
        select(ProductionOrder)
        .where(ProductionOrder.status == "completed")
        .order_by(ProductionOrder.completed_at.desc())
    )
    cost = await reports.order_cost(session, actor, last.number)
    truth["last_completed"] = last.number
    truth["last_completed_total"] = cost["total_cost_rub"]
    truth["last_completed_per_unit"] = cost["cost_per_unit_rub"]

    soy_mat = await session.scalar(select(Material).where(Material.code == "WAX-SOY"))
    avg = (await _avg_unit_cost(session))[soy_mat.id]
    truth["lavender_wax_delta"] = q_money(avg * Decimal("0.18") * Decimal("0.15"))

    friday = today + timedelta(days=(4 - today.weekday()) % 7 or 7)
    truth["next_friday"] = friday.strftime("%d.%m.%Y")
    return truth


# ---------- проверки ----------

NUM_RE = re.compile(r"-?\d[\d   ]*(?:[.,]\d+)?")


def numbers_in(text: str) -> list[Decimal]:
    out = []
    for raw in NUM_RE.findall(text):
        cleaned = raw.replace(" ", "").replace(" ", "").replace(" ", "").replace(",", ".")
        try:
            out.append(Decimal(cleaned))
        except InvalidOperation:
            continue
    return out


def contains_number(text: str, expected: Decimal) -> bool:
    tolerance = max(abs(expected) * Decimal("0.01"), Decimal("0.01"))
    return any(abs(n - expected) <= tolerance for n in numbers_in(text))


async def orders_snapshot(session) -> list[tuple[int, str]]:
    return list(
        (
            await session.execute(
                select(ProductionOrder.id, ProductionOrder.status).order_by(ProductionOrder.id)
            )
        ).all()
    )


def run_checks(spec: dict, res: Result, truth: dict, before, after) -> None:
    answer_low = res.answer.lower()
    for t in spec.get("expect_tools", []):
        res.checks[f"вызван {t}"] = t in res.tools
    for t in spec.get("forbid_tools", []):
        res.checks[f"не вызван {t}"] = t not in res.tools
    for key in spec.get("expect_numbers", []):
        res.checks[f"число {key}={truth[key]}"] = contains_number(res.answer, Decimal(str(truth[key])))
    if spec.get("expect_text_any"):
        res.checks["есть ожидаемая формулировка"] = any(
            s.lower() in answer_low for s in spec["expect_text_any"]
        )
    for s in spec.get("forbid_text", []):
        res.checks[f"нет «{s}»"] = s.lower() not in answer_low
    if "expect_action" in spec:
        res.checks["предложено действие" if spec["expect_action"] else "нет действия"] = (
            res.actions > 0
        ) == spec["expect_action"]
    if spec.get("expect_code"):
        res.checks["выполнен код"] = res.code_runs > 0
    if spec.get("expect_file"):
        res.checks["есть файл"] = bool(res.files)
    if spec.get("no_db_change"):
        res.checks["задания не изменились"] = before == after
    res.checks["ответ получен"] = res.status == "complete" and bool(res.answer.strip())


# ---------- судья ----------


async def judge(client, spec: dict, res: Result, truth: dict) -> dict[str, Any]:
    payload = {
        "question": res.question,
        "criterion": spec.get("rubric", ""),
        "reference_values": {k: str(truth[k]) for k in spec.get("expect_numbers", [])},
        "tools_called": res.tools,
        "code_interpreter_used": res.code_runs > 0,
        "files": res.files,
        "action_proposed": res.actions > 0,
        "answer": res.answer,
    }
    try:
        resp = await client.responses.create(
            model=get_settings().llm_judge_model,
            instructions=load_prompt("judge.md"),
            input=json.dumps(payload, ensure_ascii=False),
            timeout=60,
        )
        text = resp.output_text.strip()
        match = re.search(r"\{.*\}", text, re.S)
        return json.loads(match.group(0) if match else text)
    except Exception as exc:  # noqa: BLE001
        return {"score": None, "verdict": "error", "reason": f"судья недоступен: {type(exc).__name__}"}


# ---------- прогон ----------


async def run_one(spec: dict, truth: dict) -> Result:
    question = spec["question"].format(**{k: str(v) for k, v in truth.items()})
    res = Result(qid=spec["id"], user=spec["user"], question=question)
    chat = get_chat_service()
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(User.username == spec["user"]))
        conv = Conversation(user_id=user.id, title=f"[eval] {spec['id']}")
        session.add(conv)
        await session.commit()
        before = await orders_snapshot(session)

    started = time.monotonic()

    async def emit(_event):
        return None

    msg_id = await chat.run_turn(
        user=user, conversation_id=conv.id, text=question, file_ids=[], emit=emit, stop=asyncio.Event()
    )
    res.seconds = round(time.monotonic() - started, 1)
    async with SessionLocal() as session:
        msg = await session.get(Message, msg_id)
        res.answer = msg.content
        res.status = msg.status
        res.model = msg.model
        res.error = msg.meta.get("error")
        res.tools = [t["name"] for t in msg.meta.get("tool_calls", [])]
        res.code_runs = len(msg.meta.get("code", []))
        res.files = [f["filename"] for f in msg.meta.get("files", [])]
        res.actions = len(msg.meta.get("action_ids", []))
        after = await orders_snapshot(session)
    run_checks(spec, res, truth, before, after)
    return res


def render_report(results: list[Result], truth: dict, started: datetime, judged: bool) -> str:
    settings = get_settings()
    machine_ok = sum(r.machine_ok for r in results)
    scores = [r.judge["score"] for r in results if r.judge and isinstance(r.judge.get("score"), int)]
    lines = [
        f"# Прогон эталонных вопросов — {started:%Y-%m-%d %H:%M} UTC",
        "",
        f"Модели: основная `{settings.llm_primary_model}`, запасная `{settings.llm_fallback_model}`, "
        f"судья `{settings.llm_judge_model}`.",
        "",
        "## Итог",
        "",
        f"- **Машинные проверки:** {machine_ok} из {len(results)} вопросов прошли все проверки.",
    ]
    if judged:
        avg = sum(scores) / len(scores) if scores else 0
        passed = sum(1 for r in results if r.judge and r.judge.get("verdict") == "pass")
        lines.append(f"- **LLM-судья:** средняя оценка {avg:.2f} из 5, «pass» — {passed} из {len(results)}.")
    else:
        lines.append("- **LLM-судья:** не запускался (--no-judge).")
    lines += [
        "",
        "## Машинные проверки",
        "",
        "| Вопрос | Роль | Инструменты | Проверки | Время |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        failed = [k for k, v in r.checks.items() if not v]
        mark = "✅" if not failed else "❌ " + "; ".join(failed)
        lines.append(f"| `{r.qid}` | {r.user} | {', '.join(r.tools) or '—'} | {mark} | {r.seconds} с |")
    if judged:
        lines += [
            "",
            "## Оценка LLM-судьи",
            "",
            "| Вопрос | Оценка | Вердикт | Комментарий |",
            "|---|---|---|---|",
        ]
        for r in results:
            j = r.judge or {}
            lines.append(f"| `{r.qid}` | {j.get('score')} | {j.get('verdict')} | {j.get('reason', '')} |")
    lines += ["", "## Эталонные значения из БД", ""]
    lines += [f"- `{k}` = {v}" for k, v in truth.items()]
    lines += ["", "## Ответы", ""]
    for r in results:
        lines += [
            f"### {r.qid}",
            "",
            f"**Вопрос ({r.user}):** {r.question}",
            "",
            f"**Модель:** {r.model or '—'} · статус: {r.status}"
            + (f" · ошибка: {r.error}" if r.error else ""),
            "",
            r.answer or "_(пустой ответ)_",
            "",
        ]
        if r.files:
            lines += [f"Файлы: {', '.join(r.files)}", ""]
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    if not get_settings().openai_api_key:
        print("Нужен OPENAI_API_KEY в .env — прогон идёт через настоящую модель.", file=sys.stderr)
        return 2

    specs = yaml.safe_load((HERE / "questions.yaml").read_text(encoding="utf-8"))
    if args.only:
        wanted = set(args.only.split(","))
        specs = [s for s in specs if s["id"] in wanted]

    started = datetime.now(UTC)
    async with SessionLocal() as session:
        truth = await compute_truth(session)

    results = []
    for spec in specs:
        print(f"→ {spec['id']} ...", flush=True)
        res = await run_one(spec, truth)
        print(f"   {'OK' if res.machine_ok else 'FAIL'} {res.seconds}s tools={res.tools}", flush=True)
        results.append(res)

    if not args.no_judge:
        client = make_client(get_settings().openai_api_key)
        for spec, res in zip(specs, results, strict=True):
            res.judge = await judge(client, spec, res, truth)

    REPORTS.mkdir(exist_ok=True)
    report = render_report(results, truth, started, not args.no_judge)
    path = REPORTS / f"report_{started:%Y%m%d_%H%M}.md"
    path.write_text(report, encoding="utf-8")
    (REPORTS / "latest.md").write_text(report, encoding="utf-8")
    print(f"\nОтчёт: {path}")

    if not args.keep:
        async with SessionLocal() as session:
            await session.execute(delete(Conversation).where(Conversation.title.like("[eval]%")))
            await session.execute(delete(UserFact).where(UserFact.created_at >= started))
            await session.commit()
    return 0 if all(r.machine_ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
