#!/usr/bin/env python
"""Backfill for ``systems.asset``.

Derives the traded asset from the three sources using *exactly the same logic as
the importers* (``app/importers/assets.py``) and sets it ONLY on systems where
``asset IS NULL``. Existing assignments — in particular ones made through the
UI — are never overwritten, which makes the script idempotent and gives the same
result as a full re-import without rewriting trades or sweeps.

Sources and the evidence each provides:

- The research workbook: the ticker in the trade-log column ``Timeframe``, in
  some tabs only; otherwise no evidence.
- ``<engine>/results/<system>/results.xlsx``: the ``Symbol`` of the already
  selected best-config row.
- ``hadrian2/results``: base market BTC (cross-market columns are counter-checks).
- No evidence -> the documented BTC default, listed individually in the output.

Aufruf (Host, Docker-DB)::

    DATABASE_URL=postgresql+psycopg://hadrian3:hadrian3@127.0.0.1:5432/hadrian3 \
        backend/.venv/bin/python backend/scripts/backfill_assets.py            # dry-run
    ... backend/scripts/backfill_assets.py --apply                             # writes
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Optional

# Repo layout: this script lives in backend/scripts/, the package in backend/app.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.importers.assets import DEFAULT_ASSET, is_known, resolve_asset  # noqa: E402
from app.importers.hadrian2 import parse_hadrian2  # noqa: E402
from app.importers.hadrian_engine import parse_hadrian_engine  # noqa: E402
from app.importers.xlsx import parse_workbook  # noqa: E402
from app.models import System  # noqa: E402


def _resolve_xlsx() -> str:
    """Path to the workbook to read.

    ``settings.XLSX_PATH`` may carry the *container* path (``/data/...``) from
    ``.env`` while this script runs on the host. When the configured path does
    not exist, fall back to the sample workbook in the repository.
    """
    configured = settings.XLSX_PATH
    if configured and os.path.isfile(configured):
        return configured
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    return os.path.join(repo_root, "samples", "backtesting_repository_sample.xlsx")


def collect_evidence(
    xlsx_path: str, hadrian2_dir: str, engine_dir: str
) -> dict[str, str]:
    """system_name -> evidenced asset, for systems that have evidence only.

    Uses the same parsers as the import; missing sources are skipped.
    """
    evidence: dict[str, str] = {}

    if xlsx_path and os.path.isfile(xlsx_path):
        for tab in parse_workbook(xlsx_path).tabs:
            if tab.parse_status != "skipped" and tab.asset:
                evidence[tab.system_name] = tab.asset

    for directory, parser in (
        (hadrian2_dir, parse_hadrian2),
        (engine_dir, parse_hadrian_engine),
    ):
        if not directory or not os.path.isdir(directory):
            continue
        for parsed in parser(directory):
            if parsed.parse_status != "skipped" and parsed.asset:
                evidence[parsed.name] = parsed.asset

    return evidence


def backfill(
    session: Session,
    evidence: dict[str, str],
    apply_changes: bool,
) -> tuple[Counter, list[tuple[str, str]], list[str]]:
    """Fill in missing assets. Returns (distribution, changes, defaulted)."""
    systems = (
        session.execute(select(System).order_by(System.name)).scalars().all()
    )

    distribution: Counter[str] = Counter()
    changes: list[tuple[str, str]] = []
    defaulted: list[str] = []

    for system in systems:
        if system.asset:
            distribution[system.asset] += 1
            continue

        derived: Optional[str] = evidence.get(system.name)
        asset = resolve_asset(derived, context=system.name)
        if derived is None:
            defaulted.append(system.name)

        distribution[asset] += 1
        changes.append((system.name, asset))
        if apply_changes:
            system.asset = asset

    if apply_changes:
        session.commit()
    else:
        session.rollback()

    return distribution, changes, defaulted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually write the changes (default: dry run, nothing is written).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="explicitly show only, which is the default behaviour.",
    )
    parser.add_argument("--xlsx", default=None)
    parser.add_argument("--hadrian2-dir", default=settings.HADRIAN2_RESULTS_DIR)
    parser.add_argument("--engine-dir", default=settings.HADRIAN_ENGINE_RESULTS_DIR)
    parser.add_argument("--database-url", default=settings.DATABASE_URL)
    parser.add_argument(
        "--allow-missing-sources",
        action="store_true",
        help="allow --apply even when a source is missing (otherwise it aborts, "
        "so that systems do not wrongly receive the default).",
    )
    args = parser.parse_args()

    xlsx = args.xlsx or _resolve_xlsx()
    apply_changes = args.apply and not args.dry_run
    mode = "APPLY (schreibt)" if apply_changes else "DRY-RUN (schreibt nichts)"

    missing = []
    if not os.path.isfile(xlsx):
        missing.append("xlsx")
    if not os.path.isdir(args.hadrian2_dir):
        missing.append("hadrian2")
    if not os.path.isdir(args.engine_dir):
        missing.append("engine")

    print(f"Modus:     {mode}")
    print(f"DB:        {args.database_url}")
    print(f"xlsx:      {xlsx} ({'ok' if os.path.isfile(xlsx) else 'FEHLT'})")
    print(
        f"hadrian2:  {args.hadrian2_dir} "
        f"({'ok' if os.path.isdir(args.hadrian2_dir) else 'FEHLT'})"
    )
    print(
        f"engine:    {args.engine_dir} "
        f"({'ok' if os.path.isdir(args.engine_dir) else 'FEHLT'})"
    )

    if missing:
        print(
            f"\nWARNING: source(s) unreachable: {', '.join(missing)} — "
            "the affected systems would wrongly receive the default assumption."
        )
        if apply_changes and not args.allow_missing_sources:
            print("Aborting. Fix the paths or pass --allow-missing-sources.")
            return 2

    evidence = collect_evidence(xlsx, args.hadrian2_dir, args.engine_dir)
    print(f"\nevidence found across sources: {len(evidence)} systems")

    engine = create_engine(args.database_url, future=True)
    try:
        with Session(engine) as session:
            distribution, changes, defaulted = backfill(
                session, evidence, apply_changes
            )
    finally:
        engine.dispose()

    print(f"\nto set: {len(changes)} system(s)")
    for name, asset in changes:
        marker = "" if is_known(asset) else "  (unknown ticker, carried through verbatim)"
        evidence_label = "evidence" if name in evidence else f"default {DEFAULT_ASSET}"
        print(f"  {name:32} -> {asset:6} [{evidence_label}]{marker}")

    print("\ndistribution after backfill (all systems):")
    for asset, count in sorted(distribution.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {asset:6} {count:4}")
    print(f"  {'TOTAL':6} {sum(distribution.values()):4}")

    print(
        f"\nno evidence -> default {DEFAULT_ASSET}: {len(defaulted)} system(s)"
    )
    for name in defaulted:
        print(f"  {name}")

    if not apply_changes:
        print("\nNothing written. Re-run with --apply to write.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
