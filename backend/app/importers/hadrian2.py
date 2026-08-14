"""Parser for the Hadrian² research-engine result exports (Phase 5, T2/D2/D3).

Pure and DB-free: turns the ``results/`` directory of Hadrian² (three sweep
CSVs plus an ``audit/`` sub-directory) into a list of
:class:`~app.importers.programmatic_types.ParsedProgrammaticSystem`. Never
raises for per-source problems — a missing/broken file becomes an empty result
or a ``skipped``/``incomplete`` system carrying a diagnostic ``message``.

Directory contract (verified against the real data set)::

    results/
        system1_results.csv      448 sweep variants  -> carrier B-H1-101
        system2_results.csv     1296 sweep variants  -> carrier MR-H1-102
        system3_results.csv      540 sweep variants  -> split by timeframe
        audit/
            audit_master.csv               10 audited variants (rank + variant_id)
            trades_01_*.csv .. trades_10_*.csv   per-variant trade logs

Naming (D2): the ten audited variants get deterministic names by audit rank
(lowest rank per timeframe is the ``.101`` base, further ranks ``.02`` ..).
Three *reported-only* carriers (B-H1-101, MR-H1-102, MR-H4-101) hold the
pre-gate sweep grids of system1/system2/system3-4h respectively; the system3
15m/1h grids are attached to the audited bases MR-M15-101 / MR-H1-101.

Grid decomposition (D3): 124 grids / 2284 points total, all ``oos_net_ev``.
"""

from __future__ import annotations

import csv
import glob
import io
import os
from typing import Callable, Optional

from app.importers.assets import HADRIAN2_BASE_ASSET
from app.importers.csv_trades import parse_csv
from app.importers.programmatic_types import (
    ParsedProgrammaticSystem,
    ParsedSweep,
    ParsedTrade,
)

# --------------------------------------------------------------------------- #
# Naming table (D2) — audit rank -> system name.
# --------------------------------------------------------------------------- #
_RANK_TO_NAME: dict[int, str] = {
    1: "MR-M15-101",
    2: "MR-M15-101.02",
    3: "MR-M15-101.03",
    4: "MR-M15-101.04",
    5: "MR-M15-101.05",
    7: "MR-M15-101.06",
    6: "MR-H1-101",
    8: "MR-H1-101.02",
    9: "MR-H1-101.03",
    10: "MR-H1-101.04",
}

# Reported-only sweep carriers.
_CARRIER_B_H1 = "B-H1-101"       # system1 sweeps
_CARRIER_MR_H1_102 = "MR-H1-102"  # system2 sweeps
_CARRIER_MR_H4 = "MR-H4-101"     # system3 4h sweeps

# Hadrian² timeframe token -> canonical timeframe.
_TF_NORM = {"15m": "M15", "1h": "H1", "4h": "H4"}

_NAN = {"", "nan", "none", "null", "#n/a", "#div/0!", "#ref!", "#value!"}


# --------------------------------------------------------------------------- #
# Cell helpers
# --------------------------------------------------------------------------- #
def _to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if s.lower() in _NAN:
        return None
    try:
        f = float(s)
    except (ValueError, TypeError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _to_int(value: Optional[str]) -> Optional[int]:
    f = _to_float(value)
    return int(round(f)) if f is not None else None


def _to_bool(value: Optional[str]) -> bool:
    return str(value).strip().lower() == "true"


def _b01(value: Optional[str]) -> str:
    """Boolean-ish CSV cell -> '1'/'0' for compact, stable grid labels."""
    return "1" if _to_bool(value) else "0"


def _tf_from_name(name: str) -> Optional[str]:
    # PREFIX-TIMEFRAME-NUMBER[.variant]
    parts = name.split("-")
    return parts[1] if len(parts) >= 2 else None


def _read_rows(path: str) -> list[dict]:
    """Read a CSV into a list of dict rows; missing file -> empty list."""
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# --------------------------------------------------------------------------- #
# Grid decomposition (D3)
# --------------------------------------------------------------------------- #
def _build_grids(
    rows: list[dict],
    group_keys: tuple[str, ...],
    x_key: str,
    y_key: str,
    x_numeric: bool,
    y_numeric: bool,
    label_fn: Callable[[dict], str],
) -> list[ParsedSweep]:
    """Group ``rows`` into sweep grids, one per distinct ``group_keys`` tuple.

    Group order = first appearance in the CSV (deterministic). Point order is
    left as-is; the quant service applies numeric-asc / first-appearance axis
    ordering downstream.
    """
    groups: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for row in rows:
        gk = tuple((row.get(k) or "") for k in group_keys)
        if gk not in groups:
            groups[gk] = []
            order.append(gk)
        groups[gk].append(row)

    sweeps: list[ParsedSweep] = []
    for gk in order:
        grows = groups[gk]
        points: list[dict] = []
        for row in grows:
            x = _to_float(row.get(x_key)) if x_numeric else row.get(x_key)
            y = _to_float(row.get(y_key)) if y_numeric else row.get(y_key)
            points.append(
                {
                    "x": x,
                    "y": y,
                    "value": _to_float(row.get("oos_net_ev")),
                    "net_ev": _to_float(row.get("net_ev")),
                    "n_trades": _to_int(row.get("n_trades")),
                    "low_confidence": _to_bool(row.get("low_confidence")),
                    "insufficient_sample": _to_bool(row.get("insufficient_sample")),
                }
            )
        label = label_fn(dict(zip(group_keys, gk)))[:128]
        sweeps.append(
            ParsedSweep(
                label=label,
                param_x=x_key,
                param_y=y_key,
                metric="oos_net_ev",
                points=points,
            )
        )
    return sweeps


def _grids_system1(rows: list[dict]) -> list[ParsedSweep]:
    return _build_grids(
        rows,
        group_keys=("box_type", "entry_trigger", "max_trades", "regime_filter"),
        x_key="tp_type",
        y_key="sl_type",
        x_numeric=False,
        y_numeric=False,
        label_fn=lambda g: (
            f"box={g['box_type']}, trig={g['entry_trigger']}, "
            f"max={g['max_trades']}, regime={_b01(g['regime_filter'])}"
        ),
    )


def _grids_system2(rows: list[dict]) -> list[ParsedSweep]:
    return _build_grids(
        rows,
        group_keys=("zone_threshold", "entry_trigger", "volume_filter", "ema_filter"),
        x_key="tp_type",
        y_key="sl_type",
        x_numeric=False,
        y_numeric=False,
        label_fn=lambda g: (
            f"zt={g['zone_threshold']}, trig={g['entry_trigger']}, "
            f"vf={_b01(g['volume_filter'])}, ema={g['ema_filter']}"
        ),
    )


def _grids_system3(rows: list[dict]) -> list[ParsedSweep]:
    return _build_grids(
        rows,
        group_keys=("entry_trigger", "entry_level", "volume_filter"),
        x_key="tp_norm",
        y_key="sl_buffer",
        x_numeric=True,
        y_numeric=True,
        label_fn=lambda g: (
            f"trig={g['entry_trigger']}, el={g['entry_level']}, "
            f"vf={_b01(g['volume_filter'])}"
        ),
    )


# --------------------------------------------------------------------------- #
# Reported metrics
# --------------------------------------------------------------------------- #
def _audited_metrics(row: dict) -> dict:
    """reported_metrics for an audited variant (from audit_master.csv)."""
    return {
        "total_trades": _to_int(row.get("n_trades")),
        "win_rate": _to_float(row.get("win_rate")),
        "ev": _to_float(row.get("net_ev")),
        "is_ev": _to_float(row.get("is_net_ev")),
        "oos_ev": _to_float(row.get("oos_net_ev")),
        "profit_factor": _to_float(row.get("profit_factor")),
        "wf_n_windows": _to_int(row.get("wf_n_windows")),
        "wf_pct_positive": _to_float(row.get("wf_pct_positive")),
        "mc_ev_p5": _to_float(row.get("mc_ev_p5")),
        "mc_ev_p25": _to_float(row.get("mc_ev_p25")),
        "mc_ev_p50": _to_float(row.get("mc_ev_p50")),
        "mc_ev_p75": _to_float(row.get("mc_ev_p75")),
        "mc_ev_p95": _to_float(row.get("mc_ev_p95")),
        "mc_pct_pos": _to_float(row.get("mc_pct_pos")),
        "verdict": (row.get("verdict") or None),
        "source_variant_id": (row.get("variant_id") or None),
    }


def _best_sweep_variant(rows: list[dict]) -> Optional[dict]:
    """Best pre-gate variant: sufficient sample & confident, then max oos_net_ev."""
    candidates = [
        r
        for r in rows
        if not _to_bool(r.get("insufficient_sample"))
        and not _to_bool(r.get("low_confidence"))
        and _to_float(r.get("oos_net_ev")) is not None
    ]
    if not candidates:
        candidates = [r for r in rows if _to_float(r.get("oos_net_ev")) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda r: _to_float(r.get("oos_net_ev")))


def _carrier_metrics(rows: list[dict]) -> Optional[dict]:
    best = _best_sweep_variant(rows)
    if best is None:
        return {"pre_gate": True}
    return {
        "total_trades": _to_int(best.get("n_trades")),
        "win_rate": _to_float(best.get("win_rate")),
        "ev": _to_float(best.get("net_ev")),
        "is_ev": _to_float(best.get("is_net_ev")),
        "oos_ev": _to_float(best.get("oos_net_ev")),
        "profit_factor": _to_float(best.get("profit_factor")),
        "source_variant_id": (best.get("variant_id") or None),
        "pre_gate": True,
    }


# --------------------------------------------------------------------------- #
# Trades
# --------------------------------------------------------------------------- #
def _load_trades(audit_dir: str, rank: int, timeframe: Optional[str]) -> list[ParsedTrade]:
    """Load the trade log for an audit rank (file prefix ``trades_<rank:02d>_``)."""
    matches = glob.glob(os.path.join(audit_dir, f"trades_{rank:02d}_*.csv"))
    if not matches:
        return []
    path = sorted(matches)[0]
    try:
        with open(path, "rb") as fh:
            data = fh.read()
        trades, _skipped = parse_csv(data)
    except (ValueError, OSError):
        return []
    for t in trades:
        t.timeframe = timeframe  # trade files carry no timeframe column
    return trades


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def parse_hadrian2(results_dir: str) -> list[ParsedProgrammaticSystem]:
    """Parse a Hadrian² ``results`` directory into programmatic systems.

    Missing directory -> ``[]``. Missing individual files degrade gracefully
    (fewer systems / empty trade lists), never raising.
    """
    if not results_dir or not os.path.isdir(results_dir):
        return []

    audit_dir = os.path.join(results_dir, "audit")

    # --- sweep grids -------------------------------------------------------- #
    s1_rows = _read_rows(os.path.join(results_dir, "system1_results.csv"))
    s2_rows = _read_rows(os.path.join(results_dir, "system2_results.csv"))
    s3_rows = _read_rows(os.path.join(results_dir, "system3_results.csv"))

    grids_b_h1 = _grids_system1(s1_rows)
    grids_mr_h1_102 = _grids_system2(s2_rows)

    s3_by_tf: dict[str, list[dict]] = {"15m": [], "1h": [], "4h": []}
    for r in s3_rows:
        tf = (r.get("timeframe") or "").strip()
        if tf in s3_by_tf:
            s3_by_tf[tf].append(r)
    grids_s3_m15 = _grids_system3(s3_by_tf["15m"])
    grids_s3_h1 = _grids_system3(s3_by_tf["1h"])
    grids_s3_h4 = _grids_system3(s3_by_tf["4h"])

    # --- audited variants --------------------------------------------------- #
    master_by_rank: dict[int, dict] = {}
    for row in _read_rows(os.path.join(audit_dir, "audit_master.csv")):
        rank = _to_int(row.get("rank"))
        if rank is not None:
            master_by_rank[rank] = row

    systems: dict[str, ParsedProgrammaticSystem] = {}

    for rank in sorted(_RANK_TO_NAME):
        name = _RANK_TO_NAME[rank]
        tf = _tf_from_name(name)
        row = master_by_rank.get(rank)
        trades = _load_trades(audit_dir, rank, tf) if os.path.isdir(audit_dir) else []
        has_r = any(t.r_value is not None for t in trades)

        entry_rule = sl_rule = tp_rule = notes = None
        metrics = None
        if row is not None:
            entry_rule = (
                f"trigger={row.get('entry_trigger')}, "
                f"entry_level={row.get('entry_level')}, "
                f"volume_filter={row.get('volume_filter')}"
            )
            sl_rule = f"sl_buffer={row.get('sl_buffer')}"
            tp_rule = f"tp_norm={row.get('tp_norm')}"
            notes = (row.get("verdict_reason") or None)
            metrics = _audited_metrics(row)

        systems[name] = ParsedProgrammaticSystem(
            name=name,
            source_engine="hadrian2",
            timeframe=tf,
            # Base market of the Hadrian² runs is BTC. The xmkt_* columns in
            # audit_master.csv are counter-checks only.
            asset=HADRIAN2_BASE_ASSET,
            entry_rule=entry_rule,
            sl_rule=sl_rule,
            tp_rule=tp_rule,
            notes=notes,
            reported_metrics=metrics,
            parse_status="complete" if has_r else "incomplete",
            message=None if row is not None else "no audit_master row",
            trades=trades,
        )

    # Attach system3 15m/1h grids to the audited bases.
    if "MR-M15-101" in systems:
        systems["MR-M15-101"].sweeps = grids_s3_m15
    if "MR-H1-101" in systems:
        systems["MR-H1-101"].sweeps = grids_s3_h1

    # --- reported-only sweep carriers -------------------------------------- #
    def _carrier(name: str, grids: list[ParsedSweep], src_rows: list[dict]) -> None:
        if not grids and not src_rows:
            return
        systems[name] = ParsedProgrammaticSystem(
            name=name,
            source_engine="hadrian2",
            timeframe=_tf_from_name(name),
            asset=HADRIAN2_BASE_ASSET,
            notes="Reported-only pre-gate sweep carrier (best variant metrics)",
            reported_metrics=_carrier_metrics(src_rows),
            parse_status="incomplete",
            message="reported-only (pre-gate aggregate, no gated trades)",
            sweeps=grids,
        )

    _carrier(_CARRIER_B_H1, grids_b_h1, s1_rows)
    _carrier(_CARRIER_MR_H1_102, grids_mr_h1_102, s2_rows)
    _carrier(_CARRIER_MR_H4, grids_s3_h4, s3_by_tf["4h"])

    return list(systems.values())
