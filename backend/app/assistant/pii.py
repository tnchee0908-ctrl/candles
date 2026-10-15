"""Псевдонимизация ПДн перед отправкой в LLM и обратная замена в ответе.

Один сотрудник / поставщик — один псевдоним (PERSON_3, SUPPLIER_2) при любом написании:
* поставщики: «ООО Восковой двор», «Восковой двор, ООО», «ООО «Восковой двор»», «у Воскового двора»;
* сотрудники: «Петров Иван», «Петрову И.», «И. С. Петров», «Иван Сергеевич», «Петровым».

Псевдонимы хранятся в БД и не меняются между диалогами. Формат латиницей с номером выбран специально:
модель не склоняет такие токены, поэтому обратная замена надёжна.
"""

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Pseudonym, Supplier, User
from app.services.names import LEGAL_RE, supplier_core

_LEGAL = LEGAL_RE
_Q_OPEN = r"[\"«“„']?"
_Q_CLOSE = r"[\"»”“']?"
# Падежные окончания русских слов (от длинных к коротким), которые отбрасываем у основы и допускаем при поиске.
_ENDINGS = sorted(
    [
        "ого",
        "его",
        "ием",
        "ию",
        "ия",
        "ье",
        "ья",
        "ью",
        "ией",
        "ями",
        "ами",
        "ах",
        "ях",
        "ому",
        "ему",
        "ыми",
        "ими",
        "ой",
        "ей",
        "ий",
        "ый",
        "ая",
        "яя",
        "ое",
        "ее",
        "ую",
        "юю",
        "ым",
        "им",
        "ом",
        "ем",
        "ых",
        "их",
        "ые",
        "ие",
        "а",
        "я",
        "у",
        "ю",
        "е",
        "ы",
        "и",
        "о",
        "й",
    ],
    key=len,
    reverse=True,
)
_END_RE = r"(?:" + "|".join(_ENDINGS) + r")?"
_B = r"(?<![\w])"  # граница слова слева (работает с кириллицей)
_E = r"(?![\w])"  # граница слова справа

ALIAS_RE = re.compile(r"\b(PERSON|SUPPLIER)_(\d+)\b")


def _stem(word: str) -> str:
    low = word.lower()
    for end in _ENDINGS:
        if low.endswith(end) and len(low) - len(end) >= 3:
            return word[: len(word) - len(end)]
    return word


def _word(word: str) -> str:
    """Регулярка для слова в любом падеже: основа + необязательное окончание."""
    return re.escape(_stem(word)) + _END_RE


def supplier_pattern(name: str) -> str:
    words = supplier_core(name).split()
    if not words:
        return re.escape(name)
    core = r"\s+".join(_word(w) for w in words)
    if len(words) == 1:
        # Одно слово без формы и кавычек слишком легко спутать с обычным словом —
        # допускаем любые окончания, но слово должно совпасть по основе целиком.
        core = re.escape(_stem(words[0])) + _END_RE
    return _B + rf"(?:{_LEGAL}\s*)?{_Q_OPEN}\s*{core}\s*{_Q_CLOSE}(?:\s*,?\s*{_LEGAL})?" + _E


def person_pattern(full_name: str) -> str:
    parts = full_name.split()
    surname = parts[0]
    first = parts[1] if len(parts) > 1 else None
    middle = parts[2] if len(parts) > 2 else None
    s = _word(surname)
    alts = []
    if first:
        f = _word(first)
        fi = re.escape(first[0]) + r"\.\s*"
        mi = (re.escape(middle[0]) + r"\.\s*") if middle else ""
        m = _word(middle) if middle else None
        if m:
            alts += [rf"{s}\s+{f}\s+{m}", rf"{f}\s+{m}\s+{s}", rf"{f}\s+{m}"]
        alts += [rf"{s}\s+{f}", rf"{f}\s+{s}"]
        if mi:
            alts += [rf"{s}\s+{fi}{mi}", rf"{fi}{mi}{s}"]
        alts += [rf"{s}\s+{fi}", rf"{fi}{s}"]
    alts.append(s)
    return _B + "(?:" + "|".join(alts) + ")" + _E


@dataclass
class Entity:
    kind: str
    entity_id: int
    canonical: str
    alias: str
    regex: re.Pattern[str]


class Pseudonymizer:
    def __init__(self, entities: list[Entity]):
        # Сначала более длинные/специфичные имена, чтобы «Восковой двор Плюс» не съел «Восковой двор».
        self.entities = sorted(entities, key=lambda e: -len(e.canonical))
        self.by_alias = {e.alias: e for e in entities}

    @classmethod
    async def load(cls, session: AsyncSession) -> "Pseudonymizer":
        users = list(await session.scalars(select(User).order_by(User.id)))
        suppliers = list(await session.scalars(select(Supplier).order_by(Supplier.id)))
        # Номер псевдонима = id сущности: два параллельных диалога не выдадут один номер разным людям.
        # ON CONFLICT DO NOTHING — если запись уже создал соседний запрос, просто используем её.
        new_rows = [{"kind": "person", "entity_id": u.id, "alias": f"PERSON_{u.id}"} for u in users] + [
            {"kind": "supplier", "entity_id": s.id, "alias": f"SUPPLIER_{s.id}"} for s in suppliers
        ]
        if new_rows:
            await session.execute(insert(Pseudonym).values(new_rows).on_conflict_do_nothing())
            await session.commit()
        aliases = {(p.kind, p.entity_id): p.alias for p in await session.scalars(select(Pseudonym))}
        entities: list[Entity] = []
        for u in users:
            pattern = re.compile(person_pattern(u.full_name), re.IGNORECASE)
            entities.append(Entity("person", u.id, u.full_name, aliases[("person", u.id)], pattern))
        for sup in suppliers:
            pattern = re.compile(supplier_pattern(sup.name), re.IGNORECASE)
            entities.append(Entity("supplier", sup.id, sup.name, aliases[("supplier", sup.id)], pattern))
        return cls(entities)

    def mask(self, text: str) -> str:
        if not text:
            return text
        for e in self.entities:
            text = e.regex.sub(e.alias, text)
        return text

    def unmask(self, text: str) -> str:
        if not text:
            return text
        return ALIAS_RE.sub(
            lambda m: self.by_alias[m.group(0)].canonical if m.group(0) in self.by_alias else m.group(0), text
        )

    def mask_obj(self, obj: Any) -> Any:
        return _walk(obj, self.mask)

    def unmask_obj(self, obj: Any) -> Any:
        return _walk(obj, self.unmask)

    def mask_json(self, obj: Any) -> str:
        return json.dumps(self.mask_obj(obj), ensure_ascii=False, default=str)

    def alias_for(self, kind: str, entity_id: int) -> str | None:
        for e in self.entities:
            if e.kind == kind and e.entity_id == entity_id:
                return e.alias
        return None


def _walk(obj: Any, fn) -> Any:
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, dict):
        return {k: _walk(v, fn) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_walk(v, fn) for v in obj]
    return obj


_PARTIAL_ALIAS = re.compile(
    r"(?:P(?:E(?:R(?:S(?:O(?:N(?:_\d*)?)?)?)?)?)?|S(?:U(?:P(?:P(?:L(?:I(?:E(?:R(?:_\d*)?)?)?)?)?)?)?)?)$"
)


class StreamUnmasker:
    """Обратная замена в стриме: псевдоним может прийти разрезанным на части («PERS» + «ON_1»).

    Хвост, который может оказаться началом псевдонима, придерживаем до следующего куска.
    """

    def __init__(self, pseudonymizer: Pseudonymizer):
        self.p = pseudonymizer
        self.buffer = ""

    def push(self, chunk: str) -> str:
        self.buffer += chunk
        m = _PARTIAL_ALIAS.search(self.buffer)
        cut = m.start() if m else len(self.buffer)
        ready, self.buffer = self.buffer[:cut], self.buffer[cut:]
        return self.p.unmask(ready)

    def flush(self) -> str:
        out, self.buffer = self.p.unmask(self.buffer), ""
        return out
