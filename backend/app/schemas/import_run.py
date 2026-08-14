"""Pydantic schemas for the /import/xlsx endpoint (API contract §1)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TabResult(BaseModel):
    tab: Optional[str] = None
    system_name: Optional[str] = None
    status: str
    trades: int
    message: Optional[str] = None


class ImportRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    file_path: Optional[str] = None
    tabs_total: int
    systems_complete: int
    systems_incomplete: int
    tabs_skipped: int
    trades_imported: int
    tab_results: list[TabResult] = []


class ImportRequest(BaseModel):
    path: Optional[str] = None


class ProgrammaticImportRequest(BaseModel):
    hadrian2_path: Optional[str] = None
    engine_path: Optional[str] = None
