"""Нормализация названий организаций и латинская запись русских имён.

«ООО "Восковой двор"» и «Восковой двор, ООО» — один поставщик; «Petrov Ivan» — тот же Петров Иван.
"""

import re

LEGAL_FORMS = ["ООО", "ОАО", "ЗАО", "ПАО", "АО", "ИП", "НКО", "GmbH", "LLC", "Ltd", "Inc"]
LEGAL_RE = r"(?:" + "|".join(LEGAL_FORMS) + r")"


def supplier_core(name: str) -> str:
    """«ООО "Восковой двор"» / «Восковой двор, ООО» → «восковой двор» (ключ для сравнения)."""
    s = re.sub(r"[\"«»“”„']", " ", name)
    s = re.sub(r"(?<![\w])" + LEGAL_RE + r"(?![\w])", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"[,.;_]", " ", s)
    return " ".join(s.split()).lower().replace("ё", "е")


# Распространённые варианты латинской записи (паспортная, «бытовая», немецкая) для каждой буквы.
_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "(?:v|w)",
    "г": "g",
    "д": "d",
    "е": "(?:e|ye|ie)",
    "ё": "(?:e|yo|jo)",
    "ж": "(?:zh|j)",
    "з": "z",
    "и": "(?:i|y)",
    "й": "(?:y|i|j)?",
    "к": "(?:k|c)",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "(?:kh|h|x)",
    "ц": "(?:ts|c|tz)",
    "ч": "(?:ch|tch)",
    "ш": "sh",
    "щ": "(?:shch|sch)",
    "ъ": "",
    "ы": "(?:y|i)",
    "ь": "'?",
    "э": "e",
    "ю": "(?:yu|iu|ju)",
    "я": "(?:ya|ia|ja)",
}


def translit_regex(text: str, sep: str = r"[\s_]+") -> str | None:
    """Регулярка для латинской записи русского текста (без учёта регистра). None — если кириллицы нет."""
    low = text.lower()
    if not re.search(r"[а-яё]", low):
        return None
    out = []
    for ch in low:
        if ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch.isspace():
            out.append(sep)
        else:
            out.append(re.escape(ch))
    return "".join(out)
