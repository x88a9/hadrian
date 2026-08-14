"""Pure, DB-free metric computation for Hadrian3 systems.

All formulas/thresholds are ported verbatim from the canonical xlsx as
documented in docs/DECISIONS.md ("Metric formulas").

Metrics are R-based and net of costs (R = risk unit). This module has no
external dependencies beyond the stdlib and knows nothing about the ORM: any
object exposing the ``TradeLike`` attributes works (ORM Trade rows as well as
raw parser rows), via duck typing.
"""

from __future__ import annotations

from datetime import date, datetime
from statistics import mean, stdev
from typing import Iterable, List, Optional, Protocol, Sequence, runtime_checkable


@runtime_checkable
class TradeLike(Protocol):
    """Minimal shape a trade must expose to be scored.

    Both SQLAlchemy ``Trade`` instances and parser rows satisfy this by simply
    carrying these attributes.
    """

    r_value: Optional[float]
    trade_datetime: Optional[datetime]
    win_loss: Optional[str]
    entry: Optional[float]


MetricsBlock = dict


def derive_win_loss(r: Optional[float]) -> Optional[str]:
    """Classify a trade outcome from its R value (xlsx fallback rule).

    R > 0        -> "win"
    R < -0.1     -> "loss"
    R == 0       -> "draw"
    otherwise    -> None  (e.g. -0.1 <= R < 0 stays blank in the xlsx)
    """
    if r is None:
        return None
    if r > 0:
        return "win"
    if r < -0.1:
        return "loss"
    if r == 0:
        return "draw"
    return None


def _composite_grade(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    if score >= 0.6:
        return "A"
    if score >= 0.45:
        return "B"
    if score >= 0.3:
        return "C"
    if score >= 0.15:
        return "D"
    return "F"


def _ev_grade(ev: Optional[float]) -> Optional[str]:
    if ev is None:
        return None
    value = 0.8 * ev
    if value >= 0.8:
        return "A+"
    if value >= 0.6:
        return "A"
    if value >= 0.4:
        return "B"
    if value >= 0.25:
        return "C"
    if value > 0:
        return "D"
    return "F"


def _ece_grade(ece: Optional[float]) -> Optional[str]:
    if ece is None:
        return None
    if ece >= 0.7:
        return "A+"
    if ece >= 0.5:
        return "A"
    if ece >= 0.35:
        return "B"
    if ece >= 0.2:
        return "C"
    if ece > 0:
        return "D"
    return "F"


def _evol_grade(evol: Optional[float]) -> Optional[str]:
    if evol is None:
        return None
    if evol >= 0.4:
        return "A+"
    if evol >= 0.25:
        return "A"
    if evol >= 0.15:
        return "B"
    if evol >= 0.07:
        return "C"
    if evol > 0:
        return "D"
    return "F"


def _ordered_r_values(trades: Sequence[TradeLike]) -> List[float]:
    """R values in chronological order (trade_datetime asc, None date stable last).

    Identical ordering to the equity curve: Python's ``sorted`` is stable, so
    trades sharing a timestamp (or all lacking one) keep their input order.
    Only trades carrying a numeric R value contribute to the curve.
    """
    ordered = sorted(
        trades,
        key=lambda t: (t.trade_datetime is None, t.trade_datetime or datetime.min),
    )
    return [t.r_value for t in ordered if t.r_value is not None]


def _profit_factor(r_values: Sequence[float]) -> Optional[float]:
    """sum(R>0) / abs(sum(R<0)); None if no losses or no R values."""
    if not r_values:
        return None
    gains = sum(r for r in r_values if r > 0)
    losses = sum(r for r in r_values if r < 0)
    if losses == 0:
        return None
    return gains / abs(losses)


def _max_drawdown_r(ordered_r: Sequence[float]) -> Optional[float]:
    """Max peak-to-trough drop of the cumulative R curve (positive number).

    Peak starts at 0; None if there are no R values.
    """
    if not ordered_r:
        return None
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in ordered_r:
        cum += r
        if cum > peak:
            peak = cum
        drawdown = peak - cum
        if drawdown > max_dd:
            max_dd = drawdown
    return max_dd


def _skewness(r_values: Sequence[float]) -> Optional[float]:
    """Excel SKEW: n/((n-1)(n-2)) * Sum(((x-mean)/s)^3), s = STDEV.S.

    None if n < 3 or the sample standard deviation is 0.
    """
    n = len(r_values)
    if n < 3:
        return None
    s = stdev(r_values)  # sample stdev, ddof=1
    if s == 0:
        return None
    m = mean(r_values)
    acc = sum(((x - m) / s) ** 3 for x in r_values)
    return (n / ((n - 1) * (n - 2))) * acc


def _percentile_inc(r_values: Sequence[float], p: float) -> Optional[float]:
    """PERCENTILE.INC / numpy 'linear': linear interpolation on sorted data.

    ``p`` in [0, 1]. None if there are no R values.
    """
    if not r_values:
        return None
    ordered = sorted(r_values)
    n = len(ordered)
    if n == 1:
        return ordered[0]
    rank = p * (n - 1)
    lower = int(rank)  # floor for non-negative rank
    frac = rank - lower
    if lower + 1 >= n:
        return ordered[-1]
    return ordered[lower] + frac * (ordered[lower + 1] - ordered[lower])


def _empty_metrics() -> MetricsBlock:
    return {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": None,
        "ev": None,
        "total_r": None,
        "avg_win_r": None,
        "avg_loss_r": None,
        "ece": None,
        "evol": None,
        "composite_score": None,
        "composite_grade": None,
        "ev_grade": None,
        "ece_grade": None,
        "evol_grade": None,
        "first_trade_at": None,
        "last_trade_at": None,
        "span_days": None,
        "profit_factor": None,
        "max_drawdown_r": None,
        "romad": None,
        "skewness": None,
        "r_p05": None,
        "r_p25": None,
        "r_p50": None,
        "r_p75": None,
        "r_p95": None,
    }


def compute_metrics(trades: Iterable[TradeLike]) -> MetricsBlock:
    """Compute the full MetricsBlock for a set of trades.

    See docs/DECISIONS.md ("Metric formulas") for the formulas. ``first_trade_at``/``last_trade_at`` are returned as
    ``datetime | None``; serialization is left to Pydantic downstream.
    """
    trades = list(trades)
    if not trades:
        return _empty_metrics()

    # total_trades = COUNT(entry not empty)  (xlsx formula)
    total_trades = sum(1 for t in trades if t.entry is not None)

    # wins/losses come from the (normalized) win_loss attribute
    wins = sum(1 for t in trades if t.win_loss == "win")
    losses = sum(1 for t in trades if t.win_loss == "loss")
    win_rate = (wins / total_trades) if total_trades else None

    # R statistics over trades carrying a numeric R value
    r_values = [t.r_value for t in trades if t.r_value is not None]
    ev: Optional[float] = mean(r_values) if r_values else None
    total_r: Optional[float] = sum(r_values) if r_values else None

    wins_r = [r for r in r_values if r > 0]
    losses_r = [r for r in r_values if r < 0]
    avg_win_r = mean(wins_r) if wins_r else None
    avg_loss_r = mean(losses_r) if losses_r else None

    # ECE = EV / STDEV.S(R); None if <2 R values or stdev == 0
    ece: Optional[float] = None
    if len(r_values) >= 2:
        sd = stdev(r_values)  # sample stdev, ddof=1
        if sd != 0:
            ece = mean(r_values) / sd

    # Time span (in days) over trades that carry a datetime
    dts = [t.trade_datetime for t in trades if t.trade_datetime is not None]
    if dts:
        first_trade_at: Optional[datetime] = min(dts)
        last_trade_at: Optional[datetime] = max(dts)
        span_days: Optional[float] = (
            last_trade_at - first_trade_at
        ).total_seconds() / 86400
    else:
        first_trade_at = None
        last_trade_at = None
        span_days = None

    # EVol = EV * (total_trades / span_days); None if span 0/None or EV None
    evol: Optional[float] = None
    if span_days not in (None, 0) and ev is not None:
        evol = ev * (total_trades / span_days)

    # Composite = 0.4*EV + 0.4*ECE + 0.2*EVol; None if any component None
    if ev is not None and ece is not None and evol is not None:
        composite_score: Optional[float] = 0.4 * ev + 0.4 * ece + 0.2 * evol
    else:
        composite_score = None

    # --- Phase-3 additive metrics (all nullable) ------------------------- #
    profit_factor = _profit_factor(r_values)

    ordered_r = _ordered_r_values(trades)
    max_drawdown_r = _max_drawdown_r(ordered_r)
    # RoMaD = total_r / max_dd; None if max_dd is None or 0
    if total_r is not None and max_drawdown_r not in (None, 0):
        romad: Optional[float] = total_r / max_drawdown_r
    else:
        romad = None

    skewness = _skewness(r_values)

    return {
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "ev": ev,
        "total_r": total_r,
        "avg_win_r": avg_win_r,
        "avg_loss_r": avg_loss_r,
        "ece": ece,
        "evol": evol,
        "composite_score": composite_score,
        "composite_grade": _composite_grade(composite_score),
        "ev_grade": _ev_grade(ev),
        "ece_grade": _ece_grade(ece),
        "evol_grade": _evol_grade(evol),
        "first_trade_at": first_trade_at,
        "last_trade_at": last_trade_at,
        "span_days": span_days,
        "profit_factor": profit_factor,
        "max_drawdown_r": max_drawdown_r,
        "romad": romad,
        "skewness": skewness,
        "r_p05": _percentile_inc(r_values, 0.05),
        "r_p25": _percentile_inc(r_values, 0.25),
        "r_p50": _percentile_inc(r_values, 0.50),
        "r_p75": _percentile_inc(r_values, 0.75),
        "r_p95": _percentile_inc(r_values, 0.95),
    }


def split_trades(
    trades: Iterable[TradeLike], split_date: date
) -> tuple[list[TradeLike], list[TradeLike]]:
    """Partition trades into (in-sample, out-of-sample) by ``split_date``.

    trade_datetime.date() <  split_date -> IS
    trade_datetime.date() >= split_date -> OOS
    trade_datetime is None              -> neither bucket
    """
    is_trades: list[TradeLike] = []
    oos_trades: list[TradeLike] = []
    for t in trades:
        if t.trade_datetime is None:
            continue
        if t.trade_datetime.date() < split_date:
            is_trades.append(t)
        else:
            oos_trades.append(t)
    return is_trades, oos_trades


def compute_all(
    trades: Sequence[TradeLike], split_date: date
) -> dict[str, MetricsBlock]:
    """Compute the all/is/oos MetricsBlock triple used by the API."""
    trades = list(trades)
    is_trades, oos_trades = split_trades(trades, split_date)
    return {
        "all": compute_metrics(trades),
        "is": compute_metrics(is_trades),
        "oos": compute_metrics(oos_trades),
    }
