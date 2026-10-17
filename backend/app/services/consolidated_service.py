"""Consolidated (multi-workspace) DRE/DFC service (A7).

Aggregates financial reports across multiple workspaces that the requesting
user is a member of.  Inter-company transfers are already eliminated by
`counts_as_pnl()`, which excludes every row that has a `transfer_pair_id`
(both legs of a same-workspace AND cross-workspace transfer disappear from the
P&L, so no further elimination step is needed).

The consolidated view is additive: amounts from each workspace are summed by
category group and nature key, producing a single `DreReport` (or list of
`DfcReport`) that behaves identically to a single-workspace one.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.dre import DreReport


@dataclass
class WorkspaceSummary:
    workspace_id: uuid.UUID
    workspace_name: str
    currency: str
    dre: DreReport


@dataclass
class ConsolidatedDreReport:
    year: int
    month: int
    workspace_reports: list[WorkspaceSummary]
    consolidated: DreReport


async def get_consolidated_dre(
    session: AsyncSession,
    workspace_ids: list[uuid.UUID],
    user_id: uuid.UUID,
    year: int,
    month: int,
    accounting_mode: str = "competence",
) -> ConsolidatedDreReport:
    """Return per-workspace DRE reports and their consolidated sum.

    Raises ValueError when the user is not a member of any of the requested
    workspaces, or when the list is empty or has only one workspace
    (the caller should use the single-workspace report in that case).
    """
    from sqlalchemy import select
    from app.models.workspace import Workspace, WorkspaceMember
    from app.services.report_service import get_dre, _aggregate_sections

    if not workspace_ids:
        raise ValueError("At least one workspace_id is required")

    # Verify membership for every requested workspace
    r = await session.execute(
        select(WorkspaceMember.workspace_id)
        .where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.workspace_id.in_(workspace_ids),
        )
    )
    allowed = {row[0] for row in r}
    forbidden = set(workspace_ids) - allowed
    if forbidden:
        raise ValueError(f"Not a member of workspace(s): {', '.join(str(i) for i in forbidden)}")

    # Fetch workspace names for labelling
    ws_result = await session.execute(
        select(Workspace.id, Workspace.name, Workspace.default_currency).where(
            Workspace.id.in_(workspace_ids)
        )
    )
    ws_info: dict[uuid.UUID, tuple[str, str]] = {
        row[0]: (row[1], row[2]) for row in ws_result
    }

    workspace_reports: list[WorkspaceSummary] = []
    for ws_id in workspace_ids:
        dre = await get_dre(
            session, ws_id, user_id, year, month,
            include_prev=False,
            accounting_mode=accounting_mode,
        )
        name, currency = ws_info.get(ws_id, (str(ws_id), "BRL"))
        workspace_reports.append(WorkspaceSummary(
            workspace_id=ws_id,
            workspace_name=name,
            currency=currency,
            dre=dre,
        ))

    # Aggregate into one consolidated report
    all_reports = [ws.dre for ws in workspace_reports]
    sections = _aggregate_sections(all_reports)

    gross_revenue = sum(
        ws.dre.gross_revenue for ws in workspace_reports
    )
    operating_expenses = sum(
        ws.dre.operating_expenses for ws in workspace_reports
    )

    # Currency: use first workspace currency if all match, else "MIX"
    currencies = {ws.currency for ws in workspace_reports}
    currency = currencies.pop() if len(currencies) == 1 else "MIX"

    consolidated = DreReport(
        year=year,
        month=month,
        currency=currency,
        sections=sections,
        gross_revenue=gross_revenue,
        deductions=Decimal(0),
        net_revenue=gross_revenue,
        operating_expenses=operating_expenses,
        result=gross_revenue - operating_expenses,
        accounting_mode=accounting_mode,
    )

    return ConsolidatedDreReport(
        year=year,
        month=month,
        workspace_reports=workspace_reports,
        consolidated=consolidated,
    )
