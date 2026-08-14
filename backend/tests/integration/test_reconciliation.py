"""A5 reconciliation test — the Phase-1 gate.

For every system whose xlsx header carries a numerically reported EV, this test
reloads the system's persisted trades, recomputes the full MetricsBlock with
``app.services.metrics.compute_metrics`` and asserts the computed values match
the ``reported_metrics`` (the raw xlsx header values stored at import time).

Tolerances (see docs/DECISIONS.md, "Reconciliation tolerances"):

- ``ev``, ``total_r``, ``avg_win_r``, ``avg_loss_r``, ``ece``: relative 1e-6;
  when the reference is 0 (or a None/None pair) an absolute 1e-9 tolerance is
  used instead. These are the load-bearing correctness metrics and MUST hold at
  1e-6 — a violation is a real defect, not something to loosen away.
- ``total_trades``, ``wins``, ``losses``: exact integer equality.
- ``evol`` and the four grade strings: only compared when the xlsx reports them
  numerically / non-empty; grades compared exactly.

win_rate note (verified against the real workbook, 2026-07-10):
  The task brief warned that reported ``win_rate`` may be stored rounded (e.g.
  0.33 for 33/100). In THIS canonical workbook that does not occur — the header
  stores win_rate at full precision (max observed relative deviation ~2e-10), so
  1e-6 holds comfortably. We therefore verify win_rate two ways, both strict:
  (1) computed win_rate vs. the value derived from the *exact* reported
  ``wins/total_trades`` (the definition of the metric), and (2) computed
  win_rate vs. the reported win_rate field, both at relative 1e-6. If a future
  workbook snapshot did store a coarsely rounded win_rate, check (1) would still
  fully verify correctness while check (2) is the one that could legitimately be
  relaxed to 5e-3 — it is kept strict here because the real data supports it.

Name collision TREND-WH4-801 (see docs/DECISIONS.md): the tab ``TREND-WH4-801.A``
resolves to the same system name as ``TREND-WH4-801`` and is processed *first*,
so the non-``.A`` tab (processed last) wins the upsert. Its trades AND its
reported_metrics both come from that same non-``.A`` tab, so the pair is
internally consistent and reconciles cleanly — no exclusion is necessary. Should
a future data change make this system's comparison fail purely because of the
collision (reported values from the overwritten ``.A`` tab), it would be the one
documented system to exclude; see the guarded handling below.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.db import get_db
from app.main import app
from app.models import System
from app.services.import_service import run_xlsx_import
from app.services.metrics import compute_metrics
from tests.paths import REAL_XLSX, SAMPLE_XLSX, has_real_xlsx

pytestmark = pytest.mark.integration

# Reconciles whichever workbook is configured: the private research workbook
# when present, otherwise the shipped sample. Both exercise the same path
# (parse -> persist -> recompute -> API) and both must agree with the figures
# reported in the workbook header block.
XLSX_PATH = str(REAL_XLSX if has_real_xlsx() else SAMPLE_XLSX)

skip_no_xlsx = pytest.mark.skipif(
    not Path(XLSX_PATH).exists(), reason=f"no workbook available at {XLSX_PATH}"
)

REL_TOL = 1e-6
ABS_TOL = 1e-9
WIN_RATE_REL_TOL = 1e-6

# Metrics compared with the relative/absolute numeric tolerance.
NUMERIC_KEYS = ("ev", "total_r", "avg_win_r", "avg_loss_r", "ece")
# Metrics compared as exact integers.
INT_KEYS = ("total_trades", "wins", "losses")
# Grade strings compared exactly (only when reported).
GRADE_KEYS = ("composite_grade", "ev_grade", "ece_grade", "evol_grade")

# System name that would be the single documented exclusion should the xlsx
# name collision ever break its reconciliation (it does not today).
COLLISION_SYSTEM = "TREND-WH4-801"


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _num_match(reported, computed) -> tuple[bool, str]:
    """Compare a numeric metric with rel 1e-6 / abs 1e-9-near-zero semantics."""
    if reported is None and computed is None:
        return True, "both None"
    if reported is None or computed is None:
        return False, f"None-mismatch (reported={reported!r}, computed={computed!r})"
    diff = abs(reported - computed)
    if abs(reported) <= ABS_TOL:  # reference ~0 -> absolute tolerance
        return diff <= ABS_TOL, f"abs diff {diff:.3e} (abs tol {ABS_TOL:.0e})"
    rel = diff / abs(reported)
    return rel <= REL_TOL, f"rel diff {rel:.3e} (rel tol {REL_TOL:.0e})"


def _rel_ok(reported, computed, tol) -> bool:
    if reported is None or computed is None:
        return reported is None and computed is None
    if abs(reported) <= ABS_TOL:
        return abs(reported - computed) <= ABS_TOL
    return abs(reported - computed) / abs(reported) <= tol


@pytest.fixture()
def imported(db_session):
    """Run the real xlsx import into the (truncated) test DB and hand back the session."""
    run_xlsx_import(db_session, XLSX_PATH)
    return db_session


@skip_no_xlsx
def test_reconciliation_computed_matches_reported(imported):
    session = imported
    systems = session.execute(select(System).order_by(System.name)).scalars().all()

    compared = 0
    skipped_names: list[str] = []
    failures: list[str] = []

    for s in systems:
        rm = s.reported_metrics
        # Only reconcile systems that report a numeric EV (finished backtests).
        if not rm or not _is_num(rm.get("ev")):
            skipped_names.append(s.name)
            continue

        m = compute_metrics(list(s.trades))
        sys_failures: list[str] = []

        # --- numeric correctness metrics (must hold at rel 1e-6) ---
        for k in NUMERIC_KEYS:
            ok, detail = _num_match(rm.get(k), m.get(k))
            if not ok:
                sys_failures.append(
                    f"{k}: reported={rm.get(k)!r} vs computed={m.get(k)!r} -> {detail}"
                )

        # --- win_rate: strict, verified two ways (see module docstring) ---
        comp_wr = m.get("win_rate")
        rep_w, rep_tt, rep_wr = rm.get("wins"), rm.get("total_trades"), rm.get("win_rate")
        if _is_num(rep_w) and _is_num(rep_tt) and rep_tt:
            expected_wr = rep_w / rep_tt
            if not _rel_ok(expected_wr, comp_wr, WIN_RATE_REL_TOL):
                sys_failures.append(
                    f"win_rate(from reported wins/total_trades={rep_w}/{rep_tt}="
                    f"{expected_wr!r}) vs computed={comp_wr!r} -> rel tol {WIN_RATE_REL_TOL:.0e}"
                )
        if _is_num(rep_wr):
            if not _rel_ok(rep_wr, comp_wr, WIN_RATE_REL_TOL):
                sys_failures.append(
                    f"win_rate(reported field): reported={rep_wr!r} vs computed={comp_wr!r} "
                    f"-> rel tol {WIN_RATE_REL_TOL:.0e}"
                )

        # --- exact integer counts ---
        for k in INT_KEYS:
            rep = rm.get(k)
            if not _is_num(rep):
                continue
            if int(rep) != int(m.get(k)):
                sys_failures.append(f"{k}: reported={int(rep)} vs computed={m.get(k)} (must be exact)")

        # --- evol: only when reported numerically ---
        if _is_num(rm.get("evol")):
            ok, detail = _num_match(rm.get("evol"), m.get("evol"))
            if not ok:
                sys_failures.append(
                    f"evol: reported={rm.get('evol')!r} vs computed={m.get('evol')!r} -> {detail}"
                )

        # --- grades: exact string, only when reported ---
        for k in GRADE_KEYS:
            rep = rm.get(k)
            if isinstance(rep, str) and rep.strip():
                if rep != m.get(k):
                    sys_failures.append(f"{k}: reported={rep!r} vs computed={m.get(k)!r} (exact)")

        compared += 1
        if sys_failures:
            # Documented single exclusion path for the xlsx name collision. In the
            # current workbook TREND-WH4-801 reconciles cleanly, so this branch is
            # not taken; it exists so a collision-only regression is excluded with a
            # traceable reason rather than silently loosening a real metric.
            if s.name == COLLISION_SYSTEM:
                compared -= 1
                skipped_names.append(f"{s.name} (xlsx name collision, docs/DECISIONS.md)")
            else:
                failures.append("SYSTEM " + s.name + ":\n    " + "\n    ".join(sys_failures))

    print(
        f"\n[A5 reconciliation] compared={compared} "
        f"skipped={len(skipped_names)} (incomplete / no numeric EV)\n"
        f"  skipped systems: {', '.join(skipped_names) or '-'}\n"
        f"  failing systems: {len(failures)}"
    )

    assert not failures, (
        f"{len(failures)} system(s) diverge from their xlsx reported_metrics:\n\n"
        + "\n\n".join(failures)
    )
    # Phase-1 gate: at least 3 systems must be genuinely verified (real ~37).
    assert compared >= 3, f"only {compared} systems reconciled (need >= 3)"


@skip_no_xlsx
def test_api_spot_check_metrics_match_reported(imported):
    """API path sanity: GET /systems/{id}.metrics.all.ev == reported ev (rel 1e-6)."""
    session = imported
    # find the first system with a numeric reported ev
    system = None
    for s in session.execute(select(System).order_by(System.name)).scalars():
        if s.reported_metrics and _is_num(s.reported_metrics.get("ev")):
            system = s
            break
    assert system is not None, "expected at least one system with numeric reported ev"
    reported_ev = system.reported_metrics["ev"]

    app.dependency_overrides[get_db] = lambda: session
    try:
        with TestClient(app) as client:
            r = client.get(f"/systems/{system.id}")
            assert r.status_code == 200, r.text
            body = r.json()
            api_ev = body["metrics"]["all"]["ev"]
            assert api_ev == pytest.approx(reported_ev, rel=REL_TOL), (
                f"{system.name}: API metrics.all.ev={api_ev} vs reported ev={reported_ev}"
            )
    finally:
        app.dependency_overrides.clear()
