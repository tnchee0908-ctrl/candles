"""Нормализация названий организаций: «ООО "Восковой двор"» и «Восковой двор, ООО» — один поставщик."""

import re

LEGAL_FORMS = ["ООО", "ОАО", "ЗАО", "ПАО", "АО", "ИП", "НКО"]
LEGAL_RE = r"(?:" + "|".join(LEGAL_FORMS) + r")"


def supplier_core(name: str) -> str:
    """«ООО "Восковой двор"» / «Восковой двор, ООО» → «восковой двор» (ключ для сравнения)."""
    s = re.sub(r"[\"«»“”„']", " ", name)
    s = re.sub(r"(?<![\w])" + LEGAL_RE + r"(?![\w])", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"[,.;]", " ", s)
    return " ".join(s.split()).lower().replace("ё", "е")
