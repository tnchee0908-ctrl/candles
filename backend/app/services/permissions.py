"""Матрица прав. Проверка всегда на бэкенде, в сервисном слое — поэтому её не обойти ни API, ни ассистентом."""

from enum import StrEnum

from app.errors import Forbidden
from app.models import ROLE_TITLES, Role
from app.services.common import Actor


class Perm(StrEnum):
    VIEW_STOCK = "view_stock"
    MANAGE_MATERIALS = "manage_materials"
    CREATE_RECEIPT = "create_receipt"
    SET_BATCH_STATUS = "set_batch_status"
    MANAGE_RECIPES = "manage_recipes"
    MANAGE_ORDERS = "manage_orders"  # создать, запланировать, запустить, завершить, отменить
    VIEW_COSTS = "view_costs"
    VIEW_AUDIT = "view_audit"
    VIEW_MARKING = "view_marking"


PERMISSIONS: dict[Role, set[Perm]] = {
    Role.STOREKEEPER: {Perm.VIEW_STOCK, Perm.MANAGE_MATERIALS, Perm.CREATE_RECEIPT, Perm.SET_BATCH_STATUS},
    Role.TECHNOLOGIST: {
        Perm.VIEW_STOCK,
        Perm.MANAGE_RECIPES,
        Perm.MANAGE_ORDERS,
        Perm.VIEW_COSTS,
        Perm.VIEW_MARKING,
    },
    Role.MANAGER: set(Perm),
}

PERM_TITLES = {
    Perm.VIEW_STOCK: "просмотр остатков",
    Perm.MANAGE_MATERIALS: "ведение справочника материалов",
    Perm.CREATE_RECEIPT: "оформление поступлений",
    Perm.SET_BATCH_STATUS: "приёмка партий",
    Perm.MANAGE_RECIPES: "ведение рецептов",
    Perm.MANAGE_ORDERS: "управление производственными заданиями",
    Perm.VIEW_COSTS: "просмотр себестоимости",
    Perm.VIEW_AUDIT: "просмотр журнала изменений",
    Perm.VIEW_MARKING: "просмотр отправок в маркировку",
}


def has_perm(actor: Actor, perm: Perm) -> bool:
    try:
        role = Role(actor.role)
    except ValueError:
        return False
    return perm in PERMISSIONS[role]


def require(actor: Actor, perm: Perm) -> None:
    if not has_perm(actor, perm):
        role_title = ROLE_TITLES.get(actor.role, actor.role)  # type: ignore[call-overload]
        raise Forbidden(f"Недостаточно прав: роль «{role_title}» не может выполнять «{PERM_TITLES[perm]}».")


def perms_for(role: str) -> list[str]:
    try:
        return sorted(p.value for p in PERMISSIONS[Role(role)])
    except ValueError:
        return []
