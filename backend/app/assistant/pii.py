"""Псевдонимизация ПДн перед отправкой в LLM и обратная замена в ответе.

Один сотрудник / поставщик — один псевдоним (PERSON_3, SUPPLIER_2) при любом написании:
* поставщики: «ООО Восковой двор», «Восковой двор, ООО», «ООО «Восковой двор»», «у Воскового двора»,
  «Восковой_двор», латиницей «Voskovoy dvor», а также заданные варианты («Арома Трейд» для Aroma Trade GmbH);
* сотрудники: «Петров Иван», «Петрову И.», «И. С. Петров», «Иван Сергеевич», «Петровым», «Petrov Ivan».

Чтобы не путать людей и обычные слова:
* фамилия и имя совпадают только с заглавной буквы — «кузнецов» (кузнецы) не превращается в сотрудника;
* одиночная фамилия не считается сотрудником, если рядом стоит ДРУГОЕ имя или инициал:
  «Петрова Ольга», «Смирнов Пётр», «Ольга Петрова» — это однофамильцы;
* двойная фамилия («Петрова-Водкина») — другой человек: дефис не считается границей слова;
* кавычки вокруг названия поставщика снимаются только парой, иначе сломался бы CSV/JSON.

Псевдонимы хранятся в БД и не меняются между диалогами. Формат латиницей с номером выбран специально:
модель не склоняет такие токены, поэтому обратная замена надёжна.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Pseudonym, Supplier, User
from app.services.names import LEGAL_RE, supplier_core, translit_regex

# Падежные окончания русских слов (от длинных к коротким), которые отбрасываем у основы и допускаем при поиске.
_ENDINGS = sorted(
    "ого его ием ию ия ье ья ью ией ями ами ах ях ому ему ыми ими ой ей ий ый ая яя ое ее ую юю ым им ом ем "
    "ых их ые ие а я у ю е ы и о й".split(),
    key=len,
    reverse=True,
)
_END_RE = r"(?:" + "|".join(_ENDINGS) + r")?"
# Граница слова: буква/цифра или дефис рядом — значит, это часть другого слова. Подчёркивание —
# граница («Петров_отчёт.xlsx», «Восковой_двор_прайс»).
_B = r"(?<![^\W_])(?<!-)"
_E = r"(?![^\W_])(?!-)"
_SEP = r"[\s_]+"
_CAP = r"[А-ЯЁA-Z]"
# Следом идёт другое имя или инициал: «Петрова Ольга», «Смирнов П.»
_NEXT_NAME = re.compile(r"[\s_]+[А-ЯЁA-Z](?:[а-яёa-z]+|\.)")
_PREV_NAME = re.compile(r"([А-ЯЁA-Z][а-яёa-z]+)[\s_]+$")

ALIAS_RE = re.compile(r"(?<![A-Za-z0-9])(PERSON|SUPPLIER)_(\d+)(?!\d)")
_URL_RE = re.compile(r"(?:https?:|//|www\.)[^\s)\]>\"']*", re.IGNORECASE)


def _stem(word: str) -> str:
    low = word.lower()
    for end in _ENDINGS:
        if low.endswith(end) and len(low) - len(end) >= 3:
            return word[: len(word) - len(end)]
    return word


def _word_ci(word: str) -> str:
    """Слово в любом падеже и регистре (для названий поставщиков)."""
    return "(?i:" + re.escape(_stem(word)) + _END_RE + ")"


def _word_cap(word: str) -> str:
    """Слово в любом падеже, но с заглавной буквы: «Петрову», «ПЕТРОВ» — да, «петров» — нет."""
    stem = _stem(word)
    return re.escape(stem[0].upper()) + "(?i:" + re.escape(stem[1:]) + _END_RE + ")"


def _latin_cap(word: str) -> str:
    """Латинская запись без склонений, с заглавной: «Petrov», «Smirnova»."""
    rx = translit_regex(word)
    return f"(?=[A-Z])(?i:{rx})" if rx else re.escape(word)


def _initial(word: str) -> str:
    return re.escape(word[0].upper()) + r"\.\s*"


def _latin_initial(word: str) -> str:
    rx = translit_regex(word[0])
    return f"(?=[A-Z])(?i:{rx})" + r"\.\s*" if rx else _initial(word)


def _person_alts(
    surname: str,
    first: str | None,
    middle: str | None,
    word: Callable[[str], str],
    initial: Callable[[str], str],
) -> list[str]:
    s = word(surname)
    alts = []
    if first:
        f, fi = word(first), initial(first)
        m, mi = (word(middle), initial(middle)) if middle else (None, "")
        if m:
            alts += [rf"{s}{_SEP}{f}{_SEP}{m}", rf"{f}{_SEP}{m}{_SEP}{s}", rf"{f}{_SEP}{m}"]
        alts += [rf"{s}{_SEP}{f}", rf"{f}{_SEP}{s}"]
        if mi:
            alts += [rf"{s}\s+{fi}{mi}", rf"{fi}{mi}{s}"]
        alts += [rf"{s}\s+{fi}", rf"{fi}{s}"]
    return alts


def person_pattern(full_name: str) -> str:
    parts = full_name.split()
    surname = parts[0]
    first = parts[1] if len(parts) > 1 else None
    middle = parts[2] if len(parts) > 2 else None
    alts = _person_alts(surname, first, middle, _word_cap, _initial) + _person_alts(
        surname, first, middle, _latin_cap, _latin_initial
    )
    # Одиночная фамилия — отдельной группой: для неё дополнительно проверяем соседние слова.
    bare = rf"(?P<bare>{_word_cap(surname)}|{_latin_cap(surname)})"
    return _B + "(?:" + "|".join(alts + [bare]) + ")" + _E


def _core_pattern(core: str) -> str:
    words = core.replace("-", " - ").split()
    if not words:
        return ""
    parts = [r"\s*-\s*" if w == "-" else _word_ci(w) for w in words]
    out = ""
    for prev, part in zip([None, *parts], parts, strict=False):
        sep = "" if part == r"\s*-\s*" or prev == r"\s*-\s*" or prev is None else _SEP
        out += sep + part
    return out


def supplier_pattern(name: str, aliases: list[str] | None = None) -> str:
    """Название в любом написании: с формой (ООО/ИП/GmbH) или без, в кавычках-паре или без, латиницей."""
    patterns = set()
    for variant in [name, *(aliases or [])]:
        core = supplier_core(variant)
        if _core_pattern(core):
            patterns.add(_core_pattern(core))
        latin = translit_regex(core, sep=_SEP)
        if latin:
            patterns.add(f"(?i:{latin})")
    alts = sorted(patterns, key=len, reverse=True)
    if not alts:
        return re.escape(name)
    core = "(?:" + "|".join(alts) + ")"
    quoted = rf"(?:\"\s*{core}\s*\"|«\s*{core}\s*»|“\s*{core}\s*”|„\s*{core}\s*“|{core})"
    legal = rf"(?i:{LEGAL_RE})"
    return _B + rf"(?P<lp>{legal}\s*)?{quoted}(?P<ls>\s*,?\s*{legal})?" + _E


@dataclass
class Entity:
    kind: str
    entity_id: int
    canonical: str
    alias: str
    regex: re.Pattern[str]
    single_word: bool = False  # поставщик из одного слова («ИП Стеклов») легко спутать с фамилией


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
            pattern = re.compile(person_pattern(u.full_name))
            entities.append(Entity("person", u.id, u.full_name, aliases[("person", u.id)], pattern))
        for sup in suppliers:
            pattern = re.compile(supplier_pattern(sup.name, list(sup.aliases or [])))
            single = len(supplier_core(sup.name).split()) == 1
            entities.append(
                Entity(
                    "supplier", sup.id, sup.name, aliases[("supplier", sup.id)], pattern, single_word=single
                )
            )
        return cls(entities)

    def _replacer(self, e: Entity, text: str) -> Callable[[re.Match[str]], str]:
        def repl(m: re.Match[str]) -> str:
            if e.kind == "person" and m.group("bare") is not None and self._namesake(text, m):
                return m.group(0)
            if (
                e.kind == "supplier"
                and e.single_word
                and not (m.group("lp") or m.group("ls"))
                and _NEXT_NAME.match(text, m.end())
            ):
                return m.group(0)  # «Стеклова Мария» — человек, а не «ИП Стеклов»
            return e.alias

        return repl

    @staticmethod
    def _namesake(text: str, m: re.Match[str]) -> bool:
        """Фамилия без имени, а рядом — чужое имя или инициал: однофамилец, не трогаем."""
        if _NEXT_NAME.match(text, m.end()):
            return True
        before = text[: m.start()]
        prev = _PREV_NAME.search(before)
        if prev is None:
            return False
        # Слово с заглавной в начале предложения («Отчёт Петрова») — не имя; в середине — скорее имя.
        head = before[: prev.start()].rstrip()
        return bool(head) and head[-1] not in '.!?:\n«"(' and not ALIAS_RE.search(prev.group(1))

    def mask(self, text: str) -> str:
        if not text:
            return text
        for e in self.entities:
            text = e.regex.sub(self._replacer(e, text), text) if e.regex.search(text) else text
        return text

    def unmask(self, text: str) -> str:
        """Обратная замена — но не внутри адресов: настоящее имя не должно уйти во внешнюю ссылку."""
        if not text:
            return text
        out, pos = [], 0
        for url in _URL_RE.finditer(text):
            out.append(self._unmask_plain(text[pos : url.start()]))
            out.append(url.group(0))
            pos = url.end()
        out.append(self._unmask_plain(text[pos:]))
        return "".join(out)

    def _unmask_plain(self, text: str) -> str:
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
# Незаконченный адрес в конце куска: придерживаем, пока не придёт пробел (конец ссылки).
_PARTIAL_URL = re.compile(
    r"(?:h(?:t(?:t(?:p(?:s)?)?)?)?|https?:[^\s)\]>\"']*|//[^\s)\]>\"']*|www\.[^\s)\]>\"']*)$", re.I
)


class StreamUnmasker:
    """Обратная замена в стриме: псевдоним может прийти разрезанным на части («PERS» + «ON_1»).

    Хвост, который может оказаться началом псевдонима или незаконченной ссылкой, придерживаем
    до следующего куска.
    """

    def __init__(self, pseudonymizer: Pseudonymizer):
        self.p = pseudonymizer
        self.buffer = ""

    def push(self, chunk: str) -> str:
        self.buffer += chunk
        cut = len(self.buffer)
        for pattern in (_PARTIAL_ALIAS, _PARTIAL_URL):
            m = pattern.search(self.buffer)
            if m:
                cut = min(cut, m.start())
        ready, self.buffer = self.buffer[:cut], self.buffer[cut:]
        return self.p.unmask(ready)

    def flush(self) -> str:
        out, self.buffer = self.p.unmask(self.buffer), ""
        return out
