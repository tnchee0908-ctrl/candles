"""Справочники: материалы и рецепты."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.errors import Conflict, DomainError, NotFound
from app.models import Material, Recipe, RecipeItem
from app.services import audit
from app.services.common import Actor, q_qty
from app.services.permissions import Perm, require


async def list_materials(session: AsyncSession, actor: Actor) -> list[Material]:
    require(actor, Perm.VIEW_STOCK)
    return list(await session.scalars(select(Material).order_by(Material.code)))


async def create_material(
    session: AsyncSession, actor: Actor, *, code: str, name: str, unit: str
) -> Material:
    require(actor, Perm.MANAGE_MATERIALS)
    code, name, unit = code.strip().upper(), name.strip(), unit.strip()
    if not code or not name or not unit:
        raise DomainError("Заполните код, название и единицу измерения.")
    if await session.scalar(select(Material.id).where(Material.code == code)):
        raise Conflict(f"Материал с кодом {code} уже есть.")
    material = Material(code=code, name=name, unit=unit)
    session.add(material)
    await session.flush()
    audit.record(
        session,
        actor,
        entity_type="material",
        entity_id=material.id,
        entity_label=code,
        action="Материал создан",
        before=None,
        after={"code": code, "name": name, "unit": unit},
    )
    await session.commit()
    return material


async def list_recipes(session: AsyncSession, actor: Actor) -> list[Recipe]:
    require(actor, Perm.VIEW_STOCK)
    rows = await session.scalars(
        select(Recipe)
        .options(selectinload(Recipe.items).selectinload(RecipeItem.material))
        .order_by(Recipe.name)
    )
    return list(rows)


async def find_recipe(session: AsyncSession, actor: Actor, name: str) -> Recipe:
    """Поиск рецепта по названию без учёта регистра и кавычек: «Лаванда» найдёт «Свеча "Лаванда"»."""
    require(actor, Perm.VIEW_STOCK)
    cleaned = name.strip().strip("«»\"'").strip()
    if not cleaned:
        raise DomainError("Укажите название рецепта.")
    recipes = await list_recipes(session, actor)
    exact = [r for r in recipes if _norm(r.name) == _norm(cleaned)]
    if exact:
        return exact[0]
    partial = [r for r in recipes if _norm(cleaned) in _norm(r.name)]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        options = ", ".join(f"«{r.name}»" for r in partial)
        raise DomainError(f"Под «{cleaned}» подходит несколько рецептов: {options}. Уточните.")
    options = ", ".join(f"«{r.name}»" for r in recipes)
    raise NotFound(f"Рецепт «{cleaned}» не найден. Есть: {options}.")


def _norm(s: str) -> str:
    for ch in "«»\"'":
        s = s.replace(ch, "")
    return " ".join(s.lower().replace("ё", "е").split())


async def create_recipe(
    session: AsyncSession, actor: Actor, *, name: str, items: list[tuple[str, Decimal]]
) -> Recipe:
    require(actor, Perm.MANAGE_RECIPES)
    name = name.strip()
    if not name or not items:
        raise DomainError("Укажите название и хотя бы один материал.")
    if await session.scalar(select(Recipe.id).where(func.lower(Recipe.name) == name.lower())):
        raise Conflict(f"Рецепт «{name}» уже есть.")
    recipe = Recipe(name=name)
    seen = set()
    for code, qty in items:
        material = await session.scalar(select(Material).where(Material.code == code))
        if material is None:
            raise NotFound(f"Материал {code} не найден.")
        if material.id in seen:
            raise DomainError(f"Материал {code} указан дважды.")
        if qty <= 0:
            raise DomainError("Норма расхода должна быть больше нуля.")
        seen.add(material.id)
        recipe.items.append(RecipeItem(material_id=material.id, qty_per_unit=q_qty(qty)))
    session.add(recipe)
    await session.flush()
    audit.record(
        session,
        actor,
        entity_type="recipe",
        entity_id=recipe.id,
        entity_label=name,
        action="Рецепт создан",
        before=None,
        after={"items": {c: q for c, q in items}},
    )
    await session.commit()
    return recipe
