"""Request and response shapes for the strategy designer."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.strategy.definition import StrategyDefinition


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    definition: StrategyDefinition


class StrategyUpdate(BaseModel):
    definition: StrategyDefinition
    note: str | None = Field(default=None, max_length=280)


class StrategyDuplicate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class ValidateRequest(BaseModel):
    """Validation takes the raw payload, not a parsed definition.

    The whole point is to report *why* something failed to parse, so the
    endpoint cannot require it to have parsed first.
    """

    definition: dict[str, Any]


class ValidateResponse(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)
    definition: StrategyDefinition | None = None


class BacktestRequest(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    version: int | None = None
    overrides: dict[str, float] = Field(default_factory=dict)
    #: Write the result into systems/trades as an engine system, so the
    #: existing quant analytics can read it. Off by default: an exploratory run
    #: should not leave a system behind.
    persist: bool = False


class StrategyVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    definition: dict[str, Any]
    note: str | None
    created_at: datetime


class StrategySummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    asset: str
    timeframe: str
    rules: Literal["declarative", "python"]
    current_version: int
    updated_at: datetime
    last_backtest_at: datetime | None = None
    last_total_r: float | None = None


class StrategyDetailOut(StrategySummaryOut):
    definition: dict[str, Any]
    versions: list[StrategyVersionOut]


class BacktestRunSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    version: int
    status: Literal["ok", "failed"]
    error: str | None
    bars: int
    warnings: list[str]
    metrics: dict[str, Any] | None
    overrides: dict[str, float]
    system_id: int | None
    created_at: datetime


class BacktestRunOut(BacktestRunSummaryOut):
    trades: list[dict[str, Any]]
