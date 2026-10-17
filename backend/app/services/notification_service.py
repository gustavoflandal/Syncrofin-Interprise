"""Deciding what is worth telling people, and telling them once.

Generators inspect a workspace and propose notifications; `_emit` writes
them idempotently (see `Notification.dedupe_key`). Nothing here is a
request/response path: it runs from a Celery job and from a manual
"refresh" button, and it is safe to run as often as you like.

What is worth a notification is kept narrow on purpose. A bell that rings
about everything trains people to ignore it, so each generator answers a
question that has a clear action behind it:

    budget over / near the limit  -> go and look at that category
    invoice due soon / overdue    -> chase it or pay it
    bank sync failing             -> reconnect the bank
    forecast turns negative       -> move money or delay a payment
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional, cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bank_connection import BankConnection
from app.models.invoice import Invoice
from app.models.notification import Notification
from app.models.workspace import Workspace, WorkspaceMember
from app.services import budget_service, health_service, invoice_service

logger = logging.getLogger(__name__)

#: Who is told. Viewers (an accountant, a partner with read access) cannot
#: act on a budget or a bank connection, so an alert to them is noise.
NOTIFIED_ROLES = ("owner", "editor")

BUDGET_WARNING_AT = 80.0
INVOICE_DUE_SOON_DAYS = 3
FORECAST_LOOKAHEAD_DAYS = 30


@dataclass
class Draft:
    """A notification not yet addressed to anyone."""

    kind: str
    severity: str
    title: str
    body: str
    dedupe_key: str
    data: dict[str, Any] = field(default_factory=dict)
    #: Some situations belong to one person (their bank connection); most
    #: belong to the workspace. None means "every notified member".
    only_user_id: Optional[uuid.UUID] = None


def _money(value: Decimal | float, currency: str = "BRL") -> str:
    """`1234.5` -> `R$ 1.234,50` for BRL, `1,234.50 USD` otherwise."""
    amount = Decimal(str(value))
    if currency == "BRL":
        whole = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {whole}"
    return f"{amount:,.2f} {currency}"


# ---------------------------------------------------------------------------
# Generators — each returns drafts, none write
# ---------------------------------------------------------------------------
async def budget_drafts(
    session: AsyncSession, workspace: Workspace, actor_id: uuid.UUID, today: date
) -> list[Draft]:
    month = today.strftime("%Y-%m")
    drafts: list[Draft] = []
    rows = await budget_service.get_budget_vs_actual(session, workspace.id, actor_id, today)
    for row in rows:
        if not row.budget_amount or row.budget_amount <= 0:
            continue
        used = float(row.actual_amount) / float(row.budget_amount) * 100
        if used >= 100:
            drafts.append(
                Draft(
                    kind="budget_over",
                    severity="critical",
                    title=f"Orçamento estourado: {row.category_name}",
                    body=(
                        f"Você gastou {_money(row.actual_amount)} de {_money(row.budget_amount)} "
                        f"({used:.0f}%) em {row.category_name} neste mês."
                    ),
                    dedupe_key=f"budget:{row.category_id}:{month}:over",
                    data={"route": "/budgets", "category_id": str(row.category_id)},
                )
            )
        elif used >= BUDGET_WARNING_AT:
            drafts.append(
                Draft(
                    kind="budget_warning",
                    severity="warning",
                    title=f"Orçamento quase no limite: {row.category_name}",
                    body=(
                        f"{used:.0f}% de {_money(row.budget_amount)} já foram usados em "
                        f"{row.category_name} neste mês."
                    ),
                    dedupe_key=f"budget:{row.category_id}:{month}:warn",
                    data={"route": "/budgets", "category_id": str(row.category_id)},
                )
            )
    return drafts


async def invoice_drafts(
    session: AsyncSession, workspace: Workspace, today: date
) -> list[Draft]:
    invoices = (
        await session.execute(
            select(Invoice)
            .where(
                Invoice.workspace_id == workspace.id,
                Invoice.status == "open",
                Invoice.due_date <= today + timedelta(days=INVOICE_DUE_SOON_DAYS),
            )
            .options(selectinload(Invoice.allocations))
        )
    ).scalars().all()

    drafts: list[Draft] = []
    for inv in invoices:
        remaining = invoice_service.balance(inv)
        if remaining <= 0:
            continue
        who = inv.payee.name if inv.payee else "sem favorecido"
        number = f"#{inv.number}" if inv.number else ""
        receivable = inv.direction == "receivable"
        route = f"/invoices/{inv.id}"
        if inv.due_date < today:
            days = (today - inv.due_date).days
            drafts.append(
                Draft(
                    kind="invoice_overdue",
                    severity="critical" if receivable else "warning",
                    title=(
                        f"Fatura {number} vencida há {days} dia(s)"
                        if receivable
                        else f"Conta a pagar {number} vencida há {days} dia(s)"
                    ),
                    body=f"{who}: {_money(remaining, inv.currency)} em aberto.",
                    # One alert per invoice per overdue *stretch of a week*, not
                    # per day, or the inbox fills with the same sentence.
                    dedupe_key=f"invoice:{inv.id}:overdue:{days // 7}",
                    data={"route": route, "invoice_id": str(inv.id)},
                )
            )
        else:
            days = (inv.due_date - today).days
            when = "hoje" if days == 0 else f"em {days} dia(s)"
            drafts.append(
                Draft(
                    kind="invoice_due",
                    severity="warning",
                    title=(
                        f"Fatura {number} vence {when}"
                        if receivable
                        else f"Conta a pagar {number} vence {when}"
                    ),
                    body=f"{who}: {_money(remaining, inv.currency)}.",
                    dedupe_key=f"invoice:{inv.id}:due:{inv.due_date.isoformat()}",
                    data={"route": route, "invoice_id": str(inv.id)},
                )
            )
    return drafts


async def sync_drafts(session: AsyncSession, workspace: Workspace) -> list[Draft]:
    connections = (
        await session.execute(
            select(BankConnection).where(
                BankConnection.workspace_id == workspace.id,
                BankConnection.status.in_(("error", "expired")),
            )
        )
    ).scalars().all()
    drafts = []
    for conn in connections:
        name = conn.display_name or conn.institution_name
        expired = conn.status == "expired"
        drafts.append(
            Draft(
                kind="sync_failed",
                severity="warning",
                title=f"Reconecte {name}" if expired else f"Falha ao sincronizar {name}",
                body=(
                    "A autorização do banco expirou. Reconecte para voltar a importar transações."
                    if expired
                    else "A última sincronização falhou. Verifique a conexão com o banco."
                ),
                # Keyed on the status, so it is told once per failure episode and
                # again if it later fails a different way.
                dedupe_key=f"sync:{conn.id}:{conn.status}",
                data={"route": "/accounts", "connection_id": str(conn.id)},
                only_user_id=conn.user_id,
            )
        )
    return drafts


async def forecast_drafts(
    session: AsyncSession, workspace: Workspace, actor_id: uuid.UUID, today: date
) -> list[Draft]:
    forecast = await health_service.get_cashflow_forecast(
        session, workspace.id, actor_id, days=FORECAST_LOOKAHEAD_DAYS, today=today
    )
    week = forecast["first_negative_week_start"]
    if not week:
        return []
    iso_year, iso_week, _ = today.isocalendar()
    return [
        Draft(
            kind="cashflow_negative",
            severity="critical",
            title="Caixa projetado negativo",
            body=(
                f"Pelas contas recorrentes e faturas em aberto, o saldo fica negativo a partir "
                f"da semana de {date.fromisoformat(week).strftime('%d/%m')} "
                f"(mínimo de {_money(forecast['lowest_balance'], forecast['primary_currency'])})."
            ),
            dedupe_key=f"forecast:{iso_year}-W{iso_week:02d}",
            data={"route": "/", "first_negative_week_start": week},
        )
    ]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
async def recipients(session: AsyncSession, workspace_id: uuid.UUID) -> list[uuid.UUID]:
    rows = await session.execute(
        select(WorkspaceMember.user_id).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.role.in_(NOTIFIED_ROLES),
        )
    )
    return [r[0] for r in rows.all()]


async def _emit(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    drafts: list[Draft],
) -> list[Notification]:
    """Insert what is new. Returns only the rows actually created."""
    created: list[Notification] = []
    for draft in drafts:
        targets = [draft.only_user_id] if draft.only_user_id else user_ids
        for user_id in targets:
            if user_id not in user_ids:
                continue  # the owner of that bank connection is no longer a member
            exists = await session.scalar(
                select(Notification.id).where(
                    Notification.user_id == user_id,
                    Notification.dedupe_key == draft.dedupe_key,
                )
            )
            if exists:
                continue
            row = Notification(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                user_id=user_id,
                kind=draft.kind,
                severity=draft.severity,
                title=draft.title,
                body=draft.body,
                data=draft.data,
                dedupe_key=draft.dedupe_key,
            )
            session.add(row)
            created.append(row)
    await session.flush()
    return created


async def generate_for_workspace(
    session: AsyncSession, workspace: Workspace, *, today: Optional[date] = None
) -> list[Notification]:
    """Run every generator for one workspace. Idempotent; commits nothing.

    A generator that raises is skipped rather than allowed to take the
    others down: a broken forecast must not silence a budget alert.
    """
    today = today or date.today()
    user_ids = await recipients(session, workspace.id)
    if not user_ids:
        return []
    actor = user_ids[0]

    drafts: list[Draft] = []
    for name, make in (
        ("budgets", lambda: budget_drafts(session, workspace, actor, today)),
        ("invoices", lambda: invoice_drafts(session, workspace, today)),
        ("sync", lambda: sync_drafts(session, workspace)),
        ("forecast", lambda: forecast_drafts(session, workspace, actor, today)),
    ):
        try:
            drafts += await make()
        except Exception:
            logger.exception("Notification generator %r failed for workspace %s", name, workspace.id)
    return await _emit(session, workspace.id, user_ids, drafts)


# ---------------------------------------------------------------------------
# Reading (the bell)
# ---------------------------------------------------------------------------
async def list_for_user(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    unread_only: bool = False,
    limit: int = 50,
) -> list[Notification]:
    query = select(Notification).where(
        Notification.workspace_id == workspace_id, Notification.user_id == user_id
    )
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    result = await session.execute(query.order_by(Notification.created_at.desc()).limit(limit))
    return list(result.scalars().all())


async def unread_count(
    session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> int:
    from sqlalchemy import func

    return (
        await session.scalar(
            select(func.count(Notification.id)).where(
                Notification.workspace_id == workspace_id,
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
        )
    ) or 0


async def mark_read(
    session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID, notification_id: uuid.UUID
) -> bool:
    result = await session.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.workspace_id == workspace_id,
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    return (cast(CursorResult, result).rowcount or 0) > 0


async def mark_all_read(
    session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> int:
    result = await session.execute(
        update(Notification)
        .where(
            Notification.workspace_id == workspace_id,
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    return cast(CursorResult, result).rowcount or 0
