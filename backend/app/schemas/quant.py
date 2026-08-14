"""Pydantic schemas for the quant-analytics endpoints (Phase 5, D5).

Shapes mirror the three D5 response examples exactly. The pure service in
``app.services.quant`` returns plain dicts; these models validate/serialise the
API layer's assembled responses. ``pct_positive`` semantics differ by endpoint
per D5: topography keeps the raw share (0..1), walk-forward is expressed in
percent (the API layer multiplies the service's fraction by 100).
"""

from __future__ import annotations

from datetime import date
from typing import Any, List, Optional

from pydantic import BaseModel


# --------------------------------------------------------------------------- #
# Topography
# --------------------------------------------------------------------------- #

class BestPoint(BaseModel):
    """The plain grid maximum (``best``)."""

    x: Any
    y: Any
    value: float


class RobustBestPoint(BaseModel):
    """The plateau-oriented maximum — carries the ``floor`` (min of the cell and
    its neighbour minimum)."""

    x: Any
    y: Any
    value: float
    floor: Optional[float] = None


class TopographyCell(BaseModel):
    x: Any
    y: Any
    value: Optional[float] = None
    net_ev: Optional[float] = None
    n_trades: Optional[int] = None
    low_confidence: Optional[bool] = None
    insufficient_sample: Optional[bool] = None
    neighbor_min: Optional[float] = None
    neighbor_max: Optional[float] = None
    neighbor_mean: Optional[float] = None
    n_neighbors: int


class TopographyGrid(BaseModel):
    id: int
    label: Optional[str] = None
    param_x: str
    param_y: str
    metric: str
    x_values: List[Any]
    y_values: List[Any]
    cells: List[TopographyCell]
    pct_positive: Optional[float] = None
    best: Optional[BestPoint] = None
    robust_best: Optional[RobustBestPoint] = None


class TopographyResponse(BaseModel):
    system_id: int
    pre_gate: bool
    grids: List[TopographyGrid]


# --------------------------------------------------------------------------- #
# Walk-forward
# --------------------------------------------------------------------------- #

class WalkForwardWindow(BaseModel):
    index: int
    is_start: date
    is_end: date
    oos_start: date
    oos_end: date
    n_is: int
    n_oos: int
    is_ev: Optional[float] = None
    oos_ev: Optional[float] = None


class WalkForwardResponse(BaseModel):
    system_id: int
    is_months: int
    oos_months: int
    step_months: int
    min_oos_trades: int
    n_windows: int
    n_windows_evaluated: int
    # Expressed in percent (0..100) per D5; null when nothing was evaluated.
    pct_positive: Optional[float] = None
    oos_ev_mean: Optional[float] = None
    oos_ev_std: Optional[float] = None
    n_dated_trades: int
    windows: List[WalkForwardWindow]


# --------------------------------------------------------------------------- #
# Monte-Carlo
# --------------------------------------------------------------------------- #

class HistogramBin(BaseModel):
    bin_start: float
    bin_end: float
    count: int


class EquityFan(BaseModel):
    steps: List[int]
    p5: List[float]
    p25: List[float]
    p50: List[float]
    p75: List[float]
    p95: List[float]


class MonteCarloResponse(BaseModel):
    system_id: int
    n_iterations: int
    seed: int
    n_trades: int
    horizon: int
    ev_p5: Optional[float] = None
    ev_p25: Optional[float] = None
    ev_p50: Optional[float] = None
    ev_p75: Optional[float] = None
    ev_p95: Optional[float] = None
    p_ev_positive: Optional[float] = None
    ev_histogram: List[HistogramBin]
    equity_fan: EquityFan
