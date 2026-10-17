from __future__ import annotations

import uuid
from pydantic import BaseModel

from app.schemas.dre import DreReport


class WorkspaceDreSummary(BaseModel):
    workspace_id: uuid.UUID
    workspace_name: str
    currency: str
    dre: DreReport


class ConsolidatedDreResponse(BaseModel):
    year: int
    month: int
    workspace_reports: list[WorkspaceDreSummary]
    consolidated: DreReport
