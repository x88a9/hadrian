"""Strategies, versions, and running a backtest into the existing tables.

The part worth reading carefully is :func:`materialise_system`. Engine results
are meant to sit alongside the imported ones and be read by the same metrics,
walk-forward and Monte-Carlo code — that is the whole reason for persisting
them into ``systems``/``trades`` rather than keeping them in their own island.
The risk that creates is obvious and one-directional: a bug here could
overwrite an imported system whose figures are reconciled against the research
workbook. So the write refuses to touch any system whose provenance is not
``engine``, by name, before it changes anything.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.data.candles import CandleSeries, CandleSource, normalise_timeframe
from app.engine.backtest import BacktestResult, EngineTrade
from app.engine.runner import run_definition
from app.models.strategy import BacktestRun, Strategy, StrategyVersion
from app.models.system import System
from app.models.trade import Trade
from app.services import metrics as metrics_service
from app.strategy.definition import StrategyDefinition, StrategyDefinitionError
from app.strategy.render import render_condition, render_stop, render_target
from app.strategy.sandbox import SandboxError

__all__ = [
    "StrategyConflict",
    "StrategyServiceError",
    "create_strategy",
    "duplicate_strategy",
    "materialise_system",
    "metrics_for_trades",
    "run_and_record",
    "save_version",
]


class StrategyServiceError(ValueError):
    """The request cannot be carried out as asked."""


class StrategyConflict(StrategyServiceError):
    """A name is taken, or a write would touch something it must not."""


# --------------------------------------------------------------------------- #
# CRUD and versioning
# --------------------------------------------------------------------------- #


def create_strategy(
    db: Session,
    name: str,
    definition: StrategyDefinition,
    description: str | None = None,
) -> Strategy:
    if db.scalar(select(Strategy).where(Strategy.name == name)):
        raise StrategyConflict(f"a strategy named {name!r} already exists")

    strategy = Strategy(
        name=name,
        description=description,
        asset=definition.asset,
        timeframe=definition.timeframe,
        rules=definition.rules,
        current_version=1,
    )
    db.add(strategy)
    db.flush()

    db.add(
        StrategyVersion(
            strategy_id=strategy.id,
            version=1,
            definition=definition.to_json_dict(),
            note="created",
        )
    )
    db.commit()
    db.refresh(strategy)
    return strategy


def save_version(
    db: Session,
    strategy: Strategy,
    definition: StrategyDefinition,
    note: str | None = None,
) -> Strategy:
    """Write a new version. Existing versions are never modified.

    Restoring an old definition goes through here too, so the history stays
    append-only: "went back to v3" is recorded as v7, not as v3 becoming
    current again and the intervening versions becoming hard to explain.
    """
    strategy.current_version += 1
    strategy.asset = definition.asset
    strategy.timeframe = definition.timeframe
    strategy.rules = definition.rules

    db.add(
        StrategyVersion(
            strategy_id=strategy.id,
            version=strategy.current_version,
            definition=definition.to_json_dict(),
            note=note,
        )
    )
    db.commit()
    db.refresh(strategy)
    return strategy


def duplicate_strategy(db: Session, strategy: Strategy, new_name: str) -> Strategy:
    """Copy the current definition into a new strategy, starting at version 1.

    The history is deliberately not copied. A duplicate is a new line of work,
    and carrying its ancestor's versions across would make "what did v4 of this
    strategy say" ambiguous between two strategies.
    """
    current = version_or_404(db, strategy, strategy.current_version)
    definition = StrategyDefinition.from_json_dict(current.definition)
    copy = create_strategy(
        db,
        name=new_name,
        definition=definition.model_copy(update={"name": new_name}),
        description=strategy.description,
    )
    return copy


def version_or_404(db: Session, strategy: Strategy, version: int) -> StrategyVersion:
    found = db.scalar(
        select(StrategyVersion).where(
            StrategyVersion.strategy_id == strategy.id,
            StrategyVersion.version == version,
        )
    )
    if found is None:
        raise StrategyServiceError(
            f"strategy {strategy.name!r} has no version {version}"
        )
    return found


# --------------------------------------------------------------------------- #
# Running
# --------------------------------------------------------------------------- #


class _TradeRow:
    """A trade in the shape ``metrics.compute_metrics`` scores.

    The engine's own record carries more than the metrics need and spells some
    of it differently; this adapts rather than bending either side.
    """

    __slots__ = ("r_value", "trade_datetime", "win_loss", "entry")

    def __init__(self, trade: EngineTrade):
        self.r_value = trade.r_value
        self.trade_datetime = _parse_ts(trade.entry_ts)
        self.win_loss = trade.win_loss
        self.entry = trade.entry_price


def _parse_ts(raw: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None
    # The trades table stores naive timestamps; the engine works in UTC. Strip
    # the offset here so both halves of the platform compare like with like.
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _json_safe(value: object) -> object:
    """Make a MetricsBlock storable as JSONB.

    ``compute_metrics`` reports ``first_trade_at``/``last_trade_at`` as real
    ``datetime`` objects, which is right for the API layer — FastAPI encodes
    them — but not for ``json.dumps`` on the way into a JSONB column. Converted
    here rather than by changing ``metrics.py``, which is a verified module this
    phase does not touch.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def metrics_for_trades(
    trades: Sequence[EngineTrade], split_date: date | None = None
) -> dict:
    """The all/is/oos triple, from the same code every other system uses."""
    rows = [_TradeRow(t) for t in trades]
    computed = metrics_service.compute_all(
        rows, split_date or settings.IS_OOS_SPLIT_DATE
    )
    return _json_safe(computed)


def run_and_record(
    db: Session,
    strategy: Strategy,
    source: CandleSource,
    *,
    version: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    overrides: dict[str, float] | None = None,
    persist: bool = False,
) -> BacktestRun:
    """Backtest a version and store the run, whether or not it succeeded.

    A failed run is recorded rather than discarded. "This version does not run,
    and here is the traceback" is a result about the strategy, and losing it
    would mean the only evidence of a broken save is a toast the user already
    dismissed.
    """
    stored = version_or_404(db, strategy, version or strategy.current_version)
    definition = StrategyDefinition.from_json_dict(stored.definition)

    run = BacktestRun(
        strategy_id=strategy.id,
        strategy_version_id=stored.id,
        version=stored.version,
        status="ok",
        bars=0,
        warnings=[],
        trades=[],
        overrides=dict(overrides or {}),
    )

    try:
        series = source.fetch(
            definition.asset,
            normalise_timeframe(definition.timeframe),
            start or _default_start(),
            end or datetime.now(timezone.utc),
        )
        result = run_definition(definition, series, overrides=overrides)
    except (
        SandboxError,
        StrategyDefinitionError,
        ValueError,
        KeyError,
    ) as exc:
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    run.bars = result.bars
    run.warnings = list(result.warnings)
    run.trades = [t.as_dict() for t in result.trades]
    run.metrics = metrics_for_trades(result.trades)

    if persist:
        system = materialise_system(db, strategy, definition, result)
        run.system_id = system.id

    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _default_start() -> datetime:
    """Where a backtest starts when the caller does not say.

    Two years is enough to span a regime change or two on the timeframes this
    platform trades, and short enough that a first run against a cold cache
    finishes while someone is still looking at the screen.
    """
    now = datetime.now(timezone.utc)
    return now.replace(year=now.year - 2)


# --------------------------------------------------------------------------- #
# Materialising into the existing tables
# --------------------------------------------------------------------------- #


def materialise_system(
    db: Session,
    strategy: Strategy,
    definition: StrategyDefinition,
    result: BacktestResult,
) -> System:
    """Write the run's trades into ``systems``/``trades`` as an engine system.

    This is what makes an engine result a first-class citizen: once the rows
    are here, the existing metrics, IS/OOS split, walk-forward and Monte-Carlo
    code operate on it with no idea it came from the engine.

    The guard is the important line. A system carrying imported figures — the
    ones reconciled cell by cell against the research workbook — must never be
    overwritten by a backtest that happens to share its name. If the name is
    taken by anything that is not an engine system, this refuses rather than
    merging, because there is no version of merging those two things that is
    correct.
    """
    existing = db.scalar(select(System).where(System.name == strategy.name))

    if existing is not None and existing.provenance != "engine":
        raise StrategyConflict(
            f"a system named {strategy.name!r} already exists with provenance "
            f"{existing.provenance!r}. The engine will not overwrite imported "
            "results; rename the strategy or the system."
        )

    if existing is None:
        existing = System(
            name=strategy.name,
            timeframe=definition.timeframe,
            asset=definition.asset,
            status="backtest",
            provenance="engine",
            origin="ui",
            import_status="complete",
        )
        db.add(existing)
        db.flush()
    else:
        existing.timeframe = definition.timeframe
        existing.asset = definition.asset

    existing.entry_rule = _describe_rule(definition, "entry")
    existing.sl_rule = _describe_stop(definition)
    existing.tp_rule = _describe_target(definition)
    existing.notes = (
        f"Generated by the backtesting engine from strategy {strategy.name!r} "
        f"v{strategy.current_version}."
    )

    # Replace rather than append: a re-run of the same strategy supersedes the
    # previous result. Appending would silently double every trade count.
    for trade in list(existing.trades):
        db.delete(trade)
    db.flush()

    for engine_trade in result.trades:
        db.add(_to_trade_row(existing.id, definition, engine_trade))

    db.flush()
    return existing


def _to_trade_row(
    system_id: int, definition: StrategyDefinition, trade: EngineTrade
) -> Trade:
    return Trade(
        system_id=system_id,
        trade_datetime=_parse_ts(trade.entry_ts),
        zone=trade.tag,
        timeframe=definition.timeframe,
        entry=trade.entry_price,
        sl=trade.stop_price,
        exit=trade.exit_price,
        direction=trade.direction,
        r_value=trade.r_value,
        win_loss=trade.win_loss,
        # 'auto' is the existing marker for a machine-generated trade, which is
        # exactly what this is; 'ui' means a human typed it.
        source="auto",
    )


def _describe_rule(definition: StrategyDefinition, which: str) -> str:
    """A one-line summary for the systems table's free-text rule columns.

    Those columns hold prose for the imported systems and are shown side by
    side in the systems list, so an engine system that filled them with "see
    the strategy definition" left a hole in the table. A declarative rule
    renders back into something readable; a Python strategy genuinely cannot,
    and says so rather than pretending.
    """
    if definition.rules == "python":
        return f"Python strategy — {which} logic in the strategy source"

    payload = definition.to_json_dict()
    if which == "entry":
        parts = [
            render_condition(payload.get("entry_long")),
            render_condition(payload.get("entry_short")),
        ]
        labelled = [
            f"{label}: {text}"
            for label, text in zip(("long", "short"), parts)
            if text
        ]
        filters = [render_condition(f) for f in payload.get("filters") or []]
        filters = [f for f in filters if f]
        if filters:
            labelled.append("filter: " + " and ".join(filters))
        return " · ".join(labelled) or "no entry rule"

    parts = [
        render_condition(payload.get("exit_long")),
        render_condition(payload.get("exit_short")),
    ]
    labelled = [
        f"{label}: {text}" for label, text in zip(("long", "short"), parts) if text
    ]
    # An exit rule is optional: a strategy can live entirely on its stop and
    # target, and saying so is more informative than an empty cell.
    return " · ".join(labelled) or "stop and target only"


def _describe_stop(definition: StrategyDefinition) -> str:
    return render_stop(definition.risk.stop.model_dump(mode="json"))


def _describe_target(definition: StrategyDefinition) -> str | None:
    if definition.risk.target is None:
        return None
    return render_target(definition.risk.target.model_dump(mode="json"))
