"""Consolidated AP/AR queries: both sides of the ledger in one call.

`get_overview` returns aging data for receivables (what clients owe us) and
payables (what we owe suppliers) in a single async call, delegating all the
per-invoice arithmetic to `invoice_service`. The result is a Pydantic model
ready to be serialised by the API layer — no further transformation needed.
"""
import uuid
from datetime import date as _date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice
from app.models.payee import Payee, PayeeTaxId
from app.models.recurring_transaction import RecurringTransaction
from app.schemas.ar_ap import (
    AgingSide,
    ArApOverview,
    CashFlowForecast,
    ForecastBucket,
    NfeImportResult,
    NfeImportRow,
    UpcomingInvoice,
)
from app.services.invoice_forecast_service import claims_in_range
from app.services.recurring_transaction_service import get_occurrences_in_range
from app.services.invoice_service import (
    aging_summary,
    balance as _balance,
    list_invoices,
)
from app.services.nfe_parser import NFeData, NFeParseError, parse_nfe_xml

ZERO = Decimal("0")


def _side_to_schema(raw: dict) -> AgingSide:
    """Convert an `aging_summary` dict to an `AgingSide` Pydantic model.

    `aging_summary` returns `received_this_month` (cash view); we expose it
    as `collected_this_month` so the schema vocabulary is direction-neutral —
    "collected" covers both inflows (AR) and outflows (AP) without implying
    a particular direction.
    """
    upcoming = [
        UpcomingInvoice(
            id=inv.id,
            number=inv.number,
            series=inv.series,
            due_date=inv.due_date.isoformat() if inv.due_date else "",
            total=inv.total or ZERO,
            balance=_balance(inv),
            # `payee` is eagerly loaded by `aging_summary` to avoid N+1 queries
            payee_name=inv.payee.name if inv.payee else None,
        )
        for inv in raw["upcoming"]
    ]
    return AgingSide(
        outstanding=raw["outstanding"],
        overdue_amount=raw["overdue_amount"],
        overdue_count=raw["overdue_count"],
        current=raw["buckets"]["current"],
        d1_30=raw["buckets"]["d1_30"],
        d31_60=raw["buckets"]["d31_60"],
        d61_90=raw["buckets"]["d61_90"],
        d90_plus=raw["buckets"]["d90_plus"],
        # `aging_summary` names this `received_this_month`; we rename it here
        # so callers get a direction-neutral label on the schema side.
        collected_this_month=raw["received_this_month"],
        upcoming=upcoming,
    )


async def get_overview(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    today: Optional[_date] = None,
) -> ArApOverview:
    """Return aging data for both directions in a single call.

    Delegates all per-invoice arithmetic to `invoice_service.aging_summary`,
    which is the authoritative source for outstanding, overdue, and bucket
    figures. This layer only combines the two sides and computes the net
    position, which neither side knows about.
    """
    raw_r = await aging_summary(session, workspace_id, today=today, direction="receivable")
    raw_p = await aging_summary(session, workspace_id, today=today, direction="payable")

    receivable = _side_to_schema(raw_r)
    payable = _side_to_schema(raw_p)

    return ArApOverview(
        receivable=receivable,
        payable=payable,
        net_position=receivable.outstanding - payable.outstanding,
    )


async def list_titles(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    direction: str = "receivable",
    state_filter: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[Invoice], int]:
    """Paginated list of invoices for a given direction and optional state.

    Returns `(items, total_count)` so the API layer can produce a paged
    response without a second query. State filtering is applied in Python
    by `list_invoices` (see its docstring for the rationale — one honest
    pass over allocations beats a correlated subquery that would have to
    mirror `derive_state` by hand).

    `state_filter` maps to the `FACET_STATES` vocabulary (`open`, `overdue`,
    `paid`, `draft`, `all`). `None` and `"all"` both return everything.
    """
    # `list_invoices` applies offset/limit after state filtering, so we need
    # all rows to count them. We do two passes: one unlimited to count, one
    # paged to return. The workspace invoice count is small enough that this
    # is cheaper than a second SQL query that would need to duplicate the
    # Python-side filter.
    all_items = await list_invoices(
        session,
        workspace_id,
        state=state_filter if state_filter and state_filter != "all" else None,
        direction=direction,
        limit=10_000,
        offset=0,
    )
    total = len(all_items)
    offset = (page - 1) * page_size
    return all_items[offset : offset + page_size], total


def _week_label(d: _date) -> str:
    return f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"


async def get_forecast(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    currency: str,
    period: str = "month",
    num_buckets: int = 12,
    today: Optional[_date] = None,
) -> CashFlowForecast:
    """Cash-flow forecast grouped by week or month.

    Queries open invoices falling due in the next `num_buckets` periods and
    groups them by direction. Only invoices in `currency` are counted;
    multi-currency workspaces should call once per currency they care about.
    """
    today = today or _date.today()

    if period == "week":
        # Start at the beginning of the current ISO week
        start = today - timedelta(days=today.weekday())
        ends = [start + timedelta(weeks=i) for i in range(num_buckets + 1)]
        labels = [_week_label(ends[i]) for i in range(num_buckets)]
    else:
        # Start at the first of the current month
        start = today.replace(day=1)
        bucket_starts: list[_date] = []
        cur = start
        for _ in range(num_buckets + 1):
            bucket_starts.append(cur)
            # Advance one month
            if cur.month == 12:
                cur = cur.replace(year=cur.year + 1, month=1)
            else:
                cur = cur.replace(month=cur.month + 1)
        ends = bucket_starts
        labels = [f"{ends[i].year}-{ends[i].month:02d}" for i in range(num_buckets)]

    range_start = ends[0]
    range_end = ends[-1]

    claims = await claims_in_range(
        session,
        workspace_id,
        range_start,
        range_end,
        directions=("receivable", "payable"),
    )
    # Filter to the requested currency
    claims = [c for c in claims if c.currency == currency]

    # Obrigações fiscais: recorrências marcadas com tax_obligation_type. Ficam
    # num balde próprio (`taxes`) em vez de `payable`, para o usuário ver o
    # peso tributário separado das contas a pagar.
    tax_recurring = (
        await session.execute(
            select(RecurringTransaction).where(
                RecurringTransaction.workspace_id == workspace_id,
                RecurringTransaction.is_active.is_(True),
                RecurringTransaction.tax_obligation_type.isnot(None),
            )
        )
    ).scalars().all()
    tax_claims: list[tuple[_date, Decimal]] = []
    for rt in tax_recurring:
        if (rt.currency or "BRL") != currency:
            continue
        for occ_date in get_occurrences_in_range(
            rt.start_date, rt.frequency, rt.end_date,
            range_start, range_end,
            intended_day=rt.day_of_month,
            weekend_adjustment=rt.weekend_adjustment,
        ):
            tax_claims.append((occ_date, rt.amount))

    # Bucket the claims
    buckets: list[ForecastBucket] = []
    for i in range(num_buckets):
        b_start = ends[i]
        b_end = ends[i + 1]
        recv = sum(
            (c.amount for c in claims if c.direction == "receivable" and b_start <= c.due_date < b_end),
            ZERO,
        )
        pay = sum(
            (c.amount for c in claims if c.direction == "payable" and b_start <= c.due_date < b_end),
            ZERO,
        )
        taxes = sum(
            (amt for occ, amt in tax_claims if b_start <= occ < b_end), ZERO
        )
        buckets.append(
            ForecastBucket(
                label=labels[i],
                period_start=b_start,
                period_end=b_end - timedelta(days=1),
                receivable=recv,
                payable=pay,
                taxes=taxes,
                net=recv - pay - taxes,
            )
        )

    return CashFlowForecast(currency=currency, period=period, buckets=buckets)


# ── NF-e XML import ───────────────────────────────────────────────────────────


async def _find_or_create_payee(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    cnpj: Optional[str],
    name: str,
) -> Optional[uuid.UUID]:
    """Return an existing payee id matched by CNPJ, or create one."""
    if cnpj:
        # Look up by CNPJ/CPF in payee_tax_ids
        row = await session.execute(
            select(PayeeTaxId.payee_id)
            .where(
                PayeeTaxId.workspace_id == workspace_id,
                PayeeTaxId.kind.in_(["CNPJ", "CPF"]),
                PayeeTaxId.value == cnpj,
            )
            .limit(1)
        )
        payee_id = row.scalar_one_or_none()
        if payee_id:
            return payee_id

    # Fall back to name lookup (case-insensitive, trimmed)
    row = await session.execute(
        select(Payee.id)
        .where(
            Payee.workspace_id == workspace_id,
            Payee.name == name,
        )
        .limit(1)
    )
    payee_id = row.scalar_one_or_none()
    if payee_id:
        return payee_id

    # Create a new payee
    payee = Payee(
        user_id=user_id,
        workspace_id=workspace_id,
        name=name,
        type="company" if cnpj and len(cnpj) == 14 else "person",
        source="import",
    )
    session.add(payee)
    await session.flush()  # assigns payee.id

    if cnpj:
        kind = "CNPJ" if len(cnpj) == 14 else "CPF"
        session.add(
            PayeeTaxId(
                payee_id=payee.id,
                workspace_id=workspace_id,
                kind=kind,
                value=cnpj,
            )
        )
        await session.flush()

    return payee.id


async def _import_single_nfe(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    nfe: NFeData,
) -> NfeImportRow:
    """Import one parsed NF-e as a payable invoice; return the row status."""
    # Deduplication: same chave in the same workspace
    dup = await session.execute(
        select(Invoice.id).where(
            Invoice.workspace_id == workspace_id,
            Invoice.external_source == "nfe",
            Invoice.external_id == nfe.chave,
        ).limit(1)
    )
    if dup.scalar_one_or_none():
        return NfeImportRow(
            filename="",
            status="duplicate",
            chave=nfe.chave,
            supplier_name=nfe.supplier_name,
            total=nfe.total,
        )

    payee_id = await _find_or_create_payee(
        session, workspace_id, user_id, nfe.supplier_cnpj, nfe.supplier_name
    )

    inv = Invoice(
        workspace_id=workspace_id,
        user_id=user_id,
        payee_id=payee_id,
        direction="payable",
        origin="imported",
        external_source="nfe",
        external_id=nfe.chave,
        external_number=nfe.number,
        status="open",
        issue_date=nfe.issue_date,
        due_date=nfe.due_date,
        currency="BRL",
        subtotal=nfe.subtotal,
        discount=nfe.discount,
        tax_total=nfe.tax_total,
        total=nfe.total,
    )
    session.add(inv)
    await session.flush()

    return NfeImportRow(
        filename="",
        status="imported",
        invoice_id=inv.id,
        chave=nfe.chave,
        supplier_name=nfe.supplier_name,
        total=nfe.total,
    )


async def import_nfe_files(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    files: list[tuple[str, bytes]],
) -> NfeImportResult:
    """Import a batch of NF-e XML files as payable invoices.

    Each ``files`` entry is ``(filename, xml_bytes)``. Duplicates are
    detected by chave de acesso and reported as ``status="duplicate"``
    rather than raising an error, so a user can safely re-upload a set
    that was already partially imported.
    """
    rows: list[NfeImportRow] = []

    for filename, xml_bytes in files:
        try:
            nfe = parse_nfe_xml(xml_bytes)
        except NFeParseError as exc:
            rows.append(NfeImportRow(filename=filename, status="error", error=str(exc)))
            continue
        except Exception as exc:
            rows.append(NfeImportRow(filename=filename, status="error", error=f"Erro inesperado: {exc}"))
            continue

        row = await _import_single_nfe(session, workspace_id, user_id, nfe)
        row.filename = filename
        rows.append(row)

    await session.commit()

    return NfeImportResult(
        rows=rows,
        imported=sum(1 for r in rows if r.status == "imported"),
        duplicates=sum(1 for r in rows if r.status == "duplicate"),
        errors=sum(1 for r in rows if r.status == "error"),
    )
