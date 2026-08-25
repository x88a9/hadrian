"""Parameter sweeps, feeding the topography this platform already draws.

A sweep varies two declared parameters over their declared ranges and scores
each cell with one metric, producing exactly the ``parameter_sweeps`` rows the
existing topography endpoint reads. Nothing new is drawn: the point of the
topography view is the neighbourhood statistics — the flattest high plateau
rather than the single best cell — and those already exist and are already
trusted.

Why the ranges live on the parameter
------------------------------------
``ParameterSpec`` carries ``lo``/``hi``/``step`` alongside its value, so the
grid worth searching is declared once, in the strategy, rather than typed again
at sweep time. A parameter with no declared range contributes only its current
value: a partly-annotated strategy still sweeps, it just does not vary that
axis.

Cost
----
Bars are fetched and converted once for the whole grid, and a Python strategy's
entire sweep runs in a single sandbox process rather than one per cell. That
keeps a modest grid interactive. It is still synchronous and still bounded by
:data:`MAX_SWEEP_CELLS`; a grid larger than that wants a job queue, and the
right time to build one is when a sweep is asked for that actually needs it.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.candles import CandleSource, normalise_timeframe
from app.engine.runner import run_definition_grid
from app.models.parameter_sweep import ParameterSweep
from app.models.strategy import Strategy
from app.services.strategy_service import (
    StrategyServiceError,
    materialise_system,
    metrics_for_trades,
    version_or_404,
    _default_start,
)
from app.strategy.definition import StrategyDefinition

__all__ = ["MAX_SWEEP_CELLS", "SweepTooLarge", "run_sweep"]

#: Upper bound on cells in one synchronous sweep. Chosen so the slowest case —
#: a Python strategy over a long series — still finishes inside an HTTP request
#: rather than timing out halfway and leaving a half-written grid.
MAX_SWEEP_CELLS = 400

#: Metrics a cell can be scored by. Restricted to the ones where "higher is
#: better" holds, because the topography's ``best`` and ``robust_best`` take a
#: maximum and would quietly invert the meaning of, say, max drawdown.
SWEEPABLE_METRICS = (
    "ev",
    "total_r",
    "ece",
    "evol",
    "composite_score",
    "win_rate",
    "profit_factor",
    "romad",
)


class SweepTooLarge(StrategyServiceError):
    """The requested grid exceeds what a synchronous sweep will attempt."""


def run_sweep(
    db: Session,
    strategy: Strategy,
    source: CandleSource,
    *,
    param_x: str,
    param_y: str,
    metric: str = "ev",
    version: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    label: str | None = None,
) -> ParameterSweep:
    """Sweep ``param_x`` × ``param_y`` and store the grid against the system.

    The baseline — the strategy at its declared parameter values — is run too,
    and is what gets materialised into a system. The sweep hangs off that
    system, because ``parameter_sweeps`` is keyed on one and because the
    topography is a statement about a system rather than about a grid floating
    on its own.
    """
    if metric not in SWEEPABLE_METRICS:
        raise StrategyServiceError(
            f"cannot sweep on {metric!r}; higher-is-better metrics only: "
            f"{', '.join(SWEEPABLE_METRICS)}"
        )

    stored = version_or_404(db, strategy, version or strategy.current_version)
    definition = StrategyDefinition.from_json_dict(stored.definition)

    x_values = _axis(definition, param_x)
    y_values = _axis(definition, param_y)
    cells = len(x_values) * len(y_values)
    if cells > MAX_SWEEP_CELLS:
        raise SweepTooLarge(
            f"{param_x} × {param_y} is {len(x_values)}×{len(y_values)} = {cells} "
            f"cells, above the synchronous limit of {MAX_SWEEP_CELLS}. Narrow a "
            "range or widen a step."
        )

    series = source.fetch(
        definition.asset,
        normalise_timeframe(definition.timeframe),
        start or _default_start(),
        end or datetime.now(timezone.utc),
    )

    grid = [{param_x: x, param_y: y} for y in y_values for x in x_values]
    # The baseline goes last so its result is easy to pick off, and so a grid
    # that happens to contain the baseline still gets its own clean run.
    results = run_definition_grid(definition, series, grid + [{}])
    baseline = results[-1]

    points = []
    for overrides, result in zip(grid, results):
        block = metrics_for_trades(result.trades)["all"]
        points.append(
            {
                "x": overrides[param_x],
                "y": overrides[param_y],
                "value": block.get(metric),
                "n_trades": block.get("total_trades"),
                "total_r": block.get("total_r"),
                "ev": block.get("ev"),
                # Carried so a reader can tell a genuinely flat cell from one
                # that simply never traded — they look identical on a heatmap.
                "warnings": len(result.warnings),
            }
        )

    system = materialise_system(db, strategy, definition, baseline)

    existing = db.scalar(
        select(ParameterSweep).where(
            ParameterSweep.system_id == system.id,
            ParameterSweep.param_x == param_x,
            ParameterSweep.param_y == param_y,
            ParameterSweep.metric == metric,
        )
    )
    # Replace rather than accumulate: a re-run of the same axes supersedes the
    # previous grid, and two grids of the same thing would both be drawn.
    if existing is not None:
        db.delete(existing)
        db.flush()

    sweep = ParameterSweep(
        system_id=system.id,
        label=label or f"{strategy.name}: {param_x} × {param_y} ({metric})",
        param_x=param_x,
        param_y=param_y,
        metric=metric,
        points=points,
    )
    db.add(sweep)
    db.commit()
    db.refresh(sweep)
    return sweep


def _axis(definition: StrategyDefinition, name: str) -> list[float]:
    try:
        spec = definition.parameters[name]
    except KeyError:
        raise StrategyServiceError(
            f"{definition.name!r} declares no parameter {name!r}; declared: "
            f"{sorted(definition.parameters) or 'none'}"
        ) from None

    values = spec.sweep_values()
    if len(values) < 2:
        raise StrategyServiceError(
            f"parameter {name!r} has no range to sweep — give it lo, hi and step"
        )
    return values
