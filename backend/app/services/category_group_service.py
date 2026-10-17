import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.category_group import CategoryGroup
from app.schemas.category_group import CategoryGroupCreate, CategoryGroupUpdate


class CategoryGroupVisibilityError(ValueError):
    """Raised when visibility is changed for a user-created category group."""


class CategoryGroupHierarchyError(ValueError):
    """Raised when hierarchy constraints are violated."""


# Language-keyed translations for default groups
# Keys are internal identifiers, values are {lang: display_name}
DEFAULT_GROUPS_I18N = {
    "housing":   {"ru": "Жильё", "uk": "Житло", "de": "Wohnen", "fr": "Logement", "it": "Casa", "pl": "Mieszkanie", "es": "Alojamiento", "sk": "Bývanie", "en": "Housing",       "pt-BR": "Moradia",         "pt-PT": "Habitação",       "icon": "house",            "color": "#8B5CF6", "position": 0},
    "food":      {"ru": "Еда и рестораны", "uk": "Їжа та ресторани", "de": "Essen & Trinken", "fr": "Alimentation & Restaurants", "it": "Cibo e Ristoranti", "pl": "Jedzenie", "es": "Comida y Cena", "sk": "Jedlo a reštaurácie", "en": "Food & Dining", "pt-BR": "Alimentação",     "pt-PT": "Alimentação",     "icon": "utensils-crossed", "color": "#F59E0B", "position": 1},
    "transport":  {"ru": "Транспорт", "uk": "Транспорт", "de": "Transport", "fr": "Transport", "it": "Trasporti", "pl": "Transport", "es": "Transporte",     "sk": "Doprava", "en": "Transport",     "pt-BR": "Transporte",      "pt-PT": "Transportes",     "icon": "car",              "color": "#3B82F6", "position": 2},
    "lifestyle": {"ru": "Образ жизни", "uk": "Спосіб життя", "de": "Lifestyle", "fr": "Style de vie", "it": "Stile di Vita", "pl": "Styl życia", "es": "Estilo de Vida", "sk": "Životný štýl", "en": "Lifestyle",     "pt-BR": "Estilo de Vida",  "pt-PT": "Estilo de Vida",  "icon": "sparkles",         "color": "#EC4899", "position": 3},
    "income":    {"ru": "Доходы", "uk": "Доходи", "de": "Einkommen", "fr": "Revenus", "it": "Entrate", "pl": "Przychody", "es": "Ingresos",        "sk": "Príjmy", "en": "Income",        "pt-BR": "Renda",           "pt-PT": "Rendimentos",     "icon": "trending-up",      "color": "#16A34A", "position": 5},
    "other":     {"ru": "Другое", "uk": "Інше", "de": "Sonstiges", "fr": "Autres", "it": "Altro", "pl": "Inne", "es": "Otros",            "sk": "Ostatné", "en": "Other",         "pt-BR": "Outros",          "pt-PT": "Outros",          "icon": "circle-help",      "color": "#64748B", "position": 4},
}

# Maps category internal key -> group internal key
CATEGORY_TO_GROUP = {
    "housing": "housing",
    "food": "food",
    "groceries": "food",
    "transport": "transport",
    "health": "lifestyle",
    "leisure": "lifestyle",
    "education": "lifestyle",
    "subscriptions": "other",
    "salary": "income",
    "shopping": "other",
    "donations": "other",
    "personal_care": "lifestyle",
    "taxes": "other",
    "transfers": "other",
    "investments": "other",
    "other": "other",
}


# Business (empresa) groups — Brazilian chart-of-accounts structure.
# `natureza` drives DRE classification: "credit" = revenue, "debit" = expense.
DEFAULT_GROUPS_BUSINESS_I18N = {
    "biz_revenue": {"en": "Revenue",              "pt-BR": "Receitas",                  "es": "Ingresos",               "icon": "trending-up",      "color": "#16A34A", "position": 0, "natureza": "credit"},
    "biz_cogs":    {"en": "Cost of Goods/Svcs",   "pt-BR": "Custos",                    "es": "Costos",                 "icon": "package",          "color": "#F59E0B", "position": 1, "natureza": "debit"},
    "biz_opex":    {"en": "Operating Expenses",   "pt-BR": "Despesas Operacionais",     "es": "Gastos Operacionales",   "icon": "building-2",       "color": "#3B82F6", "position": 2, "natureza": "debit"},
    "biz_finex":   {"en": "Financial Expenses",   "pt-BR": "Despesas Financeiras",      "es": "Gastos Financieros",     "icon": "landmark",         "color": "#EF4444", "position": 3, "natureza": "debit"},
    "biz_taxes":   {"en": "Taxes & Levies",       "pt-BR": "Impostos e Tributos",       "es": "Impuestos y Tributos",   "icon": "receipt",          "color": "#78716C", "position": 4, "natureza": "debit"},
    "biz_xfers":   {"en": "Transfers",            "pt-BR": "Transferências",            "es": "Transferencias",         "icon": "arrow-left-right", "color": "#64748B", "position": 5, "natureza": None},
}

# Maps business category key -> business group key
CATEGORY_TO_GROUP_BUSINESS = {
    "biz_rev_products":   "biz_revenue",
    "biz_rev_services":   "biz_revenue",
    "biz_rev_financial":  "biz_revenue",
    "biz_rev_other":      "biz_revenue",
    "biz_cogs_products":  "biz_cogs",
    "biz_cogs_services":  "biz_cogs",
    "biz_opex_admin":     "biz_opex",
    "biz_opex_commercial":"biz_opex",
    "biz_opex_personnel": "biz_opex",
    "biz_opex_rent":      "biz_opex",
    "biz_opex_it":        "biz_opex",
    "biz_opex_marketing": "biz_opex",
    "biz_opex_travel":    "biz_opex",
    "biz_finex_interest": "biz_finex",
    "biz_finex_banking":  "biz_finex",
    "biz_tax_revenue":    "biz_taxes",
    "biz_tax_simples":    "biz_taxes",
    "biz_tax_income":     "biz_taxes",
    "biz_tax_other":      "biz_taxes",
    "biz_xfer_accounts":  "biz_xfers",
    "biz_xfer_invest":    "biz_xfers",
}


async def create_default_groups_business(
    session: AsyncSession,
    user_id: uuid.UUID,
    lang: str = "pt-BR",
    workspace_id: Optional[uuid.UUID] = None,
) -> dict[str, CategoryGroup]:
    """Create business category groups. Returns dict of internal_key -> group."""
    groups = {}
    for key, data in DEFAULT_GROUPS_BUSINESS_I18N.items():
        name = data.get(lang, data.get("en", key))
        group = CategoryGroup(
            user_id=user_id,
            workspace_id=workspace_id,
            name=name,
            icon=data["icon"],
            color=data["color"],
            position=data["position"],
            natureza=data.get("natureza"),
            is_system=True,
        )
        session.add(group)
        groups[key] = group
    await session.flush()
    return groups


def _resolve_group_name(key: str, lang: str) -> str:
    entry = DEFAULT_GROUPS_I18N.get(key, {})
    return str(entry.get(lang, entry.get("en", key)))


def get_effective_natureza(group: CategoryGroup) -> Optional[str]:
    """Return group's own natureza, or parent's if unset."""
    if group.natureza:
        return group.natureza
    if group.parent and group.parent.natureza:
        return group.parent.natureza
    return None


async def create_default_groups(
    session: AsyncSession,
    user_id: uuid.UUID,
    lang: str = "pt-BR",
    workspace_id: Optional[uuid.UUID] = None,
) -> dict[str, CategoryGroup]:
    """Create default category groups for a user. Returns dict of internal_key -> group. Uses flush (not commit)."""
    groups = {}
    for key, data in DEFAULT_GROUPS_I18N.items():
        name = data.get(lang, data.get("en", key))
        group = CategoryGroup(
            user_id=user_id,
            workspace_id=workspace_id,
            name=name,
            icon=data["icon"],
            color=data["color"],
            position=data["position"],
            is_system=True,
        )
        session.add(group)
        groups[key] = group
    await session.flush()
    return groups


async def get_groups(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    include_hidden: bool = False,
) -> list[CategoryGroup]:
    filters = [CategoryGroup.workspace_id == workspace_id, CategoryGroup.depth == 0]
    if not include_hidden:
        filters.append(CategoryGroup.is_hidden.is_(False))

    # Build category loaders conditionally to honour the include_hidden flag
    # (mirrors the original pattern before the hierarchy rewrite)
    if not include_hidden:
        root_cat_loader = selectinload(
            CategoryGroup.categories.and_(Category.is_hidden.is_(False))
        )
        child_cat_loader = selectinload(
            CategoryGroup.children
        ).selectinload(
            CategoryGroup.categories.and_(Category.is_hidden.is_(False))
        )
    else:
        root_cat_loader = selectinload(CategoryGroup.categories)
        child_cat_loader = selectinload(CategoryGroup.children).selectinload(
            CategoryGroup.categories
        )

    result = await session.execute(
        select(CategoryGroup)
        .where(*filters)
        .options(
            root_cat_loader,
            child_cat_loader,
            selectinload(CategoryGroup.children).selectinload(CategoryGroup.parent),
            selectinload(CategoryGroup.children).selectinload(CategoryGroup.children),
        )
        .order_by(CategoryGroup.is_hidden.asc(), CategoryGroup.position)
    )
    groups = list(result.scalars().all())
    for g in groups:
        g.effective_natureza = get_effective_natureza(g)  # type: ignore[attr-defined]
        for child in g.children:
            child.effective_natureza = get_effective_natureza(child)  # type: ignore[attr-defined]
    return groups


async def get_group(session: AsyncSession, group_id: uuid.UUID, workspace_id: uuid.UUID) -> Optional[CategoryGroup]:
    result = await session.execute(
        select(CategoryGroup)
        .where(CategoryGroup.id == group_id, CategoryGroup.workspace_id == workspace_id)
        .options(selectinload(CategoryGroup.categories))
    )
    return result.scalar_one_or_none()


async def get_group_with_children(
    session: AsyncSession,
    group_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Optional[CategoryGroup]:
    result = await session.execute(
        select(CategoryGroup)
        .where(CategoryGroup.id == group_id, CategoryGroup.workspace_id == workspace_id)
        .options(
            selectinload(CategoryGroup.categories),
            selectinload(CategoryGroup.parent),
            selectinload(CategoryGroup.children).selectinload(CategoryGroup.categories),
            selectinload(CategoryGroup.children).selectinload(CategoryGroup.children),
        )
    )
    group = result.scalar_one_or_none()
    if group:
        group.effective_natureza = get_effective_natureza(group)  # type: ignore[attr-defined]
    return group


async def create_group(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    data: CategoryGroupCreate,
) -> CategoryGroup:
    parent: Optional[CategoryGroup] = None
    depth = 0

    if data.parent_id is not None:
        parent = await get_group(session, data.parent_id, workspace_id)
        if parent is None:
            raise CategoryGroupHierarchyError("Grupo pai não encontrado neste workspace")
        if parent.depth >= 1:
            raise CategoryGroupHierarchyError(
                "Máximo de 1 nível de subgrupo (Classe → Grupo → Categoria)"
            )
        depth = parent.depth + 1

    group = CategoryGroup(
        user_id=user_id,
        workspace_id=workspace_id,
        depth=depth,
        **data.model_dump(),
    )
    session.add(group)
    await session.commit()
    created = await get_group_with_children(session, group.id, workspace_id)
    if created is None:
        raise RuntimeError("Failed to reload created category group")
    return created


async def update_group(
    session: AsyncSession, group_id: uuid.UUID, workspace_id: uuid.UUID, data: CategoryGroupUpdate
) -> Optional[CategoryGroup]:
    group = await get_group_with_children(session, group_id, workspace_id)
    if not group:
        return None

    changes = data.model_dump(exclude_unset=True)

    if "parent_id" in changes:
        new_parent_id = changes["parent_id"]
        if new_parent_id is not None:
            if new_parent_id == group_id:
                raise CategoryGroupHierarchyError("Um grupo não pode ser pai de si mesmo")
            # Prevent moving a root group that has children: its children would
            # become depth-2 "grandchildren" which the tree loader doesn't handle.
            if group.children:
                raise CategoryGroupHierarchyError("cannot_move_group_with_children")
            new_parent = await get_group(session, new_parent_id, workspace_id)
            if new_parent is None:
                raise CategoryGroupHierarchyError("Grupo pai não encontrado")
            if new_parent.depth >= 1:
                raise CategoryGroupHierarchyError("Máximo de 1 nível de subgrupo")
            changes["depth"] = new_parent.depth + 1
        else:
            changes["depth"] = 0

    if changes.get("is_hidden") is True and not group.is_system:
        raise CategoryGroupVisibilityError("Only system category groups can be hidden")

    for key, value in changes.items():
        setattr(group, key, value)

    await session.commit()
    return await get_group_with_children(session, group_id, workspace_id)


async def delete_group(session: AsyncSession, group_id: uuid.UUID, workspace_id: uuid.UUID) -> bool:
    group = await get_group_with_children(session, group_id, workspace_id)
    if not group or group.is_system:
        return False

    # Promote subgroups to root before deleting, so their categories stay
    # accessible. Without this the DB ON DELETE SET NULL would leave children
    # with depth=1 but no parent, making them invisible to get_groups().
    for child in list(group.children):
        child.depth = 0
        child.parent_id = None

    # Unlink direct categories before deleting
    await session.execute(
        update(Category).where(Category.group_id == group_id).values(group_id=None)
    )

    await session.delete(group)
    await session.commit()
    return True
