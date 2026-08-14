"""Render the figures used in the documentation.

Every figure is produced by running the platform's own analysis code — the same
``app.services.metrics`` and ``app.services.quant`` functions the API calls — over
the workbook configured for the run. By default that is the synthetic sample in
``samples/``, so the figures are reproducible from a fresh clone and no private
research is disclosed.

The numbers are therefore real output of a real pipeline over declared-synthetic
input. They demonstrate the tooling; they are not trading results.

Usage::

    python backend/scripts/generate_docs_figures.py [--xlsx PATH] [--system NAME]

Output goes to ``docs/img/`` at ~150 dpi.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.dates import date2num  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.importers.xlsx import parse_workbook  # noqa: E402
from app.services import quant  # noqa: E402
from app.services.metrics import compute_all  # noqa: E402

REPO_ROOT = _BACKEND_ROOT.parent
DEFAULT_XLSX = REPO_ROOT / "samples" / "backtesting_repository_sample.xlsx"
OUT_DIR = REPO_ROOT / "docs" / "img"
SPLIT_DATE = date(2024, 1, 1)
DPI = 150

# Palette: fixed slot order, never cycled. Text always wears text tokens.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_MUTED = "#52514e"
GRID = "#e4e3df"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
# Sequential ramp (one hue, light -> dark) for the nested Monte-Carlo bands.
BLUE_RAMP = ["#cfe0f6", "#9dc1ed", "#5c9be2", "#2a78d6"]


@dataclass
class Trade:
    """Minimal TradeLike for the metrics/quant layer."""

    trade_datetime: Optional[datetime]
    r_value: Optional[float]
    entry: Optional[float] = None
    win_loss: Optional[str] = None


def _style(ax) -> None:
    """Recessive grid and axes; the data carries the emphasis."""
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_MUTED, labelsize=9, length=0)


def _figure(width: float, height: float):
    fig, ax = plt.subplots(figsize=(width, height), dpi=DPI)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    return fig, ax


def _title(ax, title: str, subtitle: str) -> None:
    ax.set_title(title, color=INK, fontsize=13, fontweight="bold", loc="left", pad=18)
    ax.text(
        0.0,
        1.02,
        subtitle,
        transform=ax.transAxes,
        color=INK_MUTED,
        fontsize=9,
        va="bottom",
    )


def _save(fig, name: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor=SURFACE)
    plt.close(fig)
    print(f"  wrote {path.relative_to(REPO_ROOT)}")
    return path


def load_trades(xlsx: Path, system: Optional[str]) -> tuple[str, list[Trade]]:
    """Parse the workbook and return the trades of one system.

    Without ``--system``, picks the system covering the widest date range, so
    that both the IS/OOS split and the walk-forward schedule have enough history
    on each side to be worth showing.
    """
    result = parse_workbook(str(xlsx))
    by_name: dict[str, list[Trade]] = {}
    span: dict[str, float] = {}
    for tab in result.tabs:
        trades = [
            Trade(
                trade_datetime=t.trade_datetime,
                r_value=t.r_value,
                entry=t.entry,
                win_loss=t.win_loss,
            )
            for t in tab.trades
        ]
        dated = [t for t in trades if t.trade_datetime and t.r_value is not None]
        if dated:
            by_name[tab.system_name] = trades
            stamps = [t.trade_datetime for t in dated]
            span[tab.system_name] = (max(stamps) - min(stamps)).total_seconds()

    if not by_name:
        raise SystemExit(f"no system with dated, numeric-R trades in {xlsx}")

    if system:
        if system not in by_name:
            raise SystemExit(
                f"system {system!r} not found. Available: {', '.join(sorted(by_name))}"
            )
        name = system
    else:
        name = max(by_name, key=lambda n: (span[n], len(by_name[n])))
    return name, by_name[name]


# --------------------------------------------------------------------------- #
# Figure 1 — equity curve, in-sample vs out-of-sample
# --------------------------------------------------------------------------- #
def figure_equity_curve(name: str, trades: Sequence[Trade]) -> Path:
    dated = sorted(
        (t for t in trades if t.trade_datetime and t.r_value is not None),
        key=lambda t: t.trade_datetime,
    )
    xs, ys, cum = [], [], 0.0
    for t in dated:
        cum += t.r_value
        xs.append(t.trade_datetime)
        ys.append(cum)

    split_dt = datetime.combine(SPLIT_DATE, datetime.min.time())
    is_idx = [i for i, x in enumerate(xs) if x < split_dt]
    metrics = compute_all(list(trades), SPLIT_DATE)

    fig, ax = _figure(9.0, 4.6)

    if is_idx:
        cut = is_idx[-1] + 1
        ax.plot(xs[:cut], ys[:cut], color=INK_MUTED, linewidth=2, zorder=3)
        # Overlap by one point so the line reads as continuous.
        ax.plot(xs[cut - 1 :], ys[cut - 1 :], color=BLUE, linewidth=2, zorder=3)
        ax.axvspan(split_dt, xs[-1], color=BLUE, alpha=0.05, zorder=1)
        ax.axvline(split_dt, color=INK_MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=2)
        ax.annotate(
            f"split {SPLIT_DATE.isoformat()}",
            xy=(split_dt, max(ys)),
            xytext=(6, -2),
            textcoords="offset points",
            color=INK_MUTED,
            fontsize=9,
            va="top",
        )
    else:
        ax.plot(xs, ys, color=BLUE, linewidth=2, zorder=3)

    ax.axhline(0, color=GRID, linewidth=1, zorder=1)
    ax.set_ylabel("cumulative R", color=INK_MUTED, fontsize=10)

    def _ev(block: str) -> str:
        ev = metrics[block]["ev"]
        n = metrics[block]["total_trades"]
        return "n/a" if ev is None else f"EV {ev:+.2f}R  ·  n={n}"

    _title(
        ax,
        f"Equity curve — {name}",
        f"in-sample {_ev('is')}      out-of-sample {_ev('oos')}",
    )
    ax.legend(
        handles=[
            Patch(facecolor=INK_MUTED, label="in-sample"),
            Patch(facecolor=BLUE, label="out-of-sample"),
        ],
        loc="upper left",
        frameon=False,
        fontsize=9,
        labelcolor=INK_MUTED,
    )
    fig.autofmt_xdate()
    return _save(fig, "equity-curve-is-oos.png")


# --------------------------------------------------------------------------- #
# Figure 2 — walk-forward window schedule
# --------------------------------------------------------------------------- #
def figure_walk_forward(name: str, trades: Sequence[Trade]) -> Path:
    wf = quant.walk_forward(list(trades), is_months=6, oos_months=3)
    windows = wf["windows"]
    if not windows:
        raise SystemExit("walk_forward produced no windows")

    fig, ax = _figure(9.0, 0.42 * len(windows) + 2.2)

    for w in windows:
        y = -w["index"]
        is_start = date2num(w["is_start"])
        is_end = date2num(w["is_end"])
        oos_end = date2num(w["oos_end"])
        ax.add_patch(
            Rectangle(
                (is_start, y - 0.32),
                is_end - is_start,
                0.64,
                facecolor=INK_MUTED,
                edgecolor=SURFACE,
                linewidth=2,  # 2px surface gap between adjacent fills
                zorder=3,
            )
        )
        ax.add_patch(
            Rectangle(
                (is_end, y - 0.32),
                oos_end - is_end,
                0.64,
                facecolor=BLUE,
                edgecolor=SURFACE,
                linewidth=2,
                zorder=3,
            )
        )
        ev = w["oos_ev"]
        ax.annotate(
            f"OOS EV {ev:+.2f}R" if ev is not None else "no OOS trades",
            xy=(oos_end, y),
            xytext=(8, 0),
            textcoords="offset points",
            color=AQUA if (ev or 0) > 0 else INK_MUTED,
            fontsize=8.5,
            va="center",
        )

    ax.set_ylim(-len(windows) + 0.3, 1.0)
    ax.set_yticks([-w["index"] for w in windows])
    ax.set_yticklabels([f"window {w['index'] + 1}" for w in windows])
    last_oos = date2num(windows[-1]["oos_end"])
    last_is_end = date2num(windows[-1]["is_end"])
    ax.set_xlim(
        date2num(windows[0]["is_start"]),
        last_oos + (last_oos - last_is_end) * 1.6,
    )
    ax.xaxis_date()
    ax.grid(axis="y", visible=False)

    pct = wf["pct_positive"]
    pct_txt = "n/a" if pct is None else f"{pct * 100:.0f}%"
    _title(
        ax,
        f"Walk-forward windows — {name}",
        f"{wf['is_months']}-month in-sample, {wf['oos_months']}-month out-of-sample, "
        f"stepping {wf['step_months']} months  ·  "
        f"{wf['n_windows_evaluated']} of {wf['n_windows']} windows evaluated  ·  "
        f"{pct_txt} with positive OOS EV",
    )
    ax.legend(
        handles=[
            Patch(facecolor=INK_MUTED, label="in-sample window"),
            Patch(facecolor=BLUE, label="out-of-sample window"),
        ],
        loc="upper right",
        frameon=False,
        fontsize=9,
        labelcolor=INK_MUTED,
    )
    fig.autofmt_xdate()
    return _save(fig, "walk-forward-windows.png")


# --------------------------------------------------------------------------- #
# Figure 3 — Monte-Carlo equity fan
# --------------------------------------------------------------------------- #
def figure_monte_carlo(name: str, trades: Sequence[Trade]) -> Path:
    r_values = [t.r_value for t in trades if t.r_value is not None]
    mc = quant.monte_carlo(r_values, n_iterations=2000, seed=42)
    fan = mc["equity_fan"]
    if not fan or not fan.get("steps"):
        raise SystemExit("monte_carlo produced no fan")

    steps = fan["steps"]
    fig, ax = _figure(9.0, 4.6)

    # Nested bands from one hue, light (widest) to dark (narrowest).
    for (lo, hi), shade, label in (
        (("p5", "p95"), BLUE_RAMP[0], "5th–95th percentile"),
        (("p25", "p75"), BLUE_RAMP[1], "25th–75th percentile"),
    ):
        ax.fill_between(
            steps,
            fan[lo],
            fan[hi],
            color=shade,
            linewidth=0,
            zorder=2,
            label=label,
        )
    ax.plot(
        steps, fan["p50"], color=BLUE_RAMP[3], linewidth=2, zorder=3,
        label="median path",
    )
    ax.axhline(0, color=INK_MUTED, linewidth=1, linestyle=(0, (4, 3)), zorder=2)

    ax.set_xlabel("trades", color=INK_MUTED, fontsize=10)
    ax.set_ylabel("cumulative R", color=INK_MUTED, fontsize=10)

    p_pos = mc["p_ev_positive"]
    _title(
        ax,
        f"Monte-Carlo equity fan — {name}",
        f"2,000 bootstrap resamples of {len(r_values)} trades, seed 42  ·  "
        f"EV p5 {mc['ev_p5']:+.2f}R / p50 {mc['ev_p50']:+.2f}R / p95 {mc['ev_p95']:+.2f}R"
        f"  ·  {p_pos * 100:.0f}% of runs end with positive EV",
    )
    ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK_MUTED)
    return _save(fig, "monte-carlo-fan.png")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--system", default=None, help="system name to plot")
    args = parser.parse_args()

    if not args.xlsx.is_file():
        raise SystemExit(f"workbook not found: {args.xlsx}")

    name, trades = load_trades(args.xlsx, args.system)
    print(f"source : {args.xlsx}")
    print(f"system : {name} ({len(trades)} trades)")

    figure_equity_curve(name, trades)
    figure_walk_forward(name, trades)
    figure_monte_carlo(name, trades)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
