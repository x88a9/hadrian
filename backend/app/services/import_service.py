"""Persistence layer for the xlsx import.

Parses the workbook (app/importers/xlsx) and upserts the result into Postgres
in a single transaction. Idempotent by system name (see docs/DECISIONS.md,
"Import idempotency"
"Idempotenz"): a re-import fully replaces a system's ``source='manual'`` trades
(delete + insert); ``source='auto'`` trades (Phase 2) are never touched.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import os

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.importers.assets import resolve_asset
from app.importers.csv_trades import parse_csv
from app.importers.hadrian2 import parse_hadrian2
from app.importers.hadrian_engine import parse_hadrian_engine
from app.importers.programmatic_types import ParsedProgrammaticSystem
from app.importers.xlsx import ParsedTab, ParsedTrade, parse_workbook
from app.models import ImportRun, ParameterSweep, System, Trade


def split_name(name: str) -> tuple[Optional[str], Optional[str]]:
    """Derive (prefix, timeframe) from a system name like ``B-H1-801``.

    prefix   = segment before the first "-"
    timeframe = second segment if present
    Names without the pattern -> (None, None) resp. (prefix, None).
    """
    if "-" not in name:
        return None, None
    segments = name.split("-")
    prefix = segments[0].strip() or None
    timeframe = segments[1].strip() if len(segments) >= 2 and segments[1].strip() else None
    return prefix, timeframe


# Backwards-compatible private alias (kept for internal call sites).
_split_name = split_name


def _upsert_system(session: Session, tab: ParsedTab) -> System:
    system = session.execute(
        select(System).where(System.name == tab.system_name)
    ).scalar_one_or_none()

    prefix, timeframe = split_name(tab.system_name)

    if system is None:
        system = System(name=tab.system_name)
        session.add(system)
        overrides: set[str] = set()
    else:
        # Field-level protection: fields overridden in the UI are left alone.
        overrides = set(system.user_overrides or [])

    system.prefix = prefix
    if "timeframe" not in overrides:
        system.timeframe = timeframe
    if "asset" not in overrides:
        system.asset = resolve_asset(tab.asset, context=f"xlsx:{tab.tab_name}")
    if "entry_rule" not in overrides:
        system.entry_rule = tab.entry_rule
    if "sl_rule" not in overrides:
        system.sl_rule = tab.sl_rule
    if "tp_rule" not in overrides:
        system.tp_rule = tab.tp_rule
    # reported_metrics/import_status/prefix bleiben Import-Hoheit.
    system.reported_metrics = tab.reported_metrics
    system.import_status = tab.parse_status  # "complete" | "incomplete"

    # Ensure the system has a PK before we attach trades to it.
    session.flush()
    return system


def _replace_manual_trades(session: Session, system: System, parsed: list[ParsedTrade]) -> int:
    # Drop only manual trades; auto trades (Phase 2) survive.
    session.execute(
        delete(Trade).where(Trade.system_id == system.id, Trade.source == "manual")
    )
    for p in parsed:
        session.add(
            Trade(
                system_id=system.id,
                trade_datetime=p.trade_datetime,
                zone=p.zone,
                timeframe=p.timeframe,
                entry=p.entry,
                sl=p.sl,
                exit=p.exit,
                direction=p.direction,
                r_value=p.r_value,
                win_loss=p.win_loss,
                source="manual",
            )
        )
    return len(parsed)


def run_xlsx_import(session: Session, path: str) -> ImportRun:
    """Parse ``path`` and persist all tabs. Returns the committed ImportRun.

    Everything runs in one transaction; on any error we roll back and
    re-raise (the API layer turns that into a 500).
    """
    started_at = datetime.now(timezone.utc)
    try:
        result = parse_workbook(path)

        tabs_total = len(result.tabs)
        systems_complete = 0
        systems_incomplete = 0
        tabs_skipped = 0
        trades_imported = 0
        tab_results: list[dict] = []

        for tab in result.tabs:
            if tab.parse_status == "skipped":
                tabs_skipped += 1
                tab_results.append(
                    {
                        "tab": tab.tab_name,
                        "system_name": tab.system_name,
                        "status": "skipped",
                        "trades": 0,
                        "message": tab.message,
                    }
                )
                continue

            # Re-Import-Schutz (Phase 6, D1): UI-Systeme komplett unangetastet.
            existing = session.execute(
                select(System).where(System.name == tab.system_name)
            ).scalar_one_or_none()
            if existing is not None and existing.origin == "ui":
                tabs_skipped += 1
                tab_results.append(
                    {
                        "tab": tab.tab_name,
                        "system_name": tab.system_name,
                        "status": "skipped",
                        "trades": 0,
                        "message": "protected: origin=ui",
                    }
                )
                continue

            system = _upsert_system(session, tab)
            n = _replace_manual_trades(session, system, tab.trades)
            trades_imported += n

            if tab.parse_status == "complete":
                systems_complete += 1
            else:
                systems_incomplete += 1

            tab_results.append(
                {
                    "tab": tab.tab_name,
                    "system_name": tab.system_name,
                    "status": tab.parse_status,
                    "trades": n,
                    "message": tab.message,
                }
            )

        import_run = ImportRun(
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            file_path=path,
            tabs_total=tabs_total,
            systems_complete=systems_complete,
            systems_incomplete=systems_incomplete,
            tabs_skipped=tabs_skipped,
            trades_imported=trades_imported,
            tab_results=tab_results,
        )
        session.add(import_run)
        session.commit()
        session.refresh(import_run)
        return import_run
    except Exception:
        session.rollback()
        raise


def _upsert_system_by_name(session: Session, system_name: str) -> System:
    """Upsert a system by name for the CSV import (D3): missing -> create with
    empty rules; prefix/timeframe derived from the name; ``import_status`` is
    set to ``complete`` (client-provided auto data). Das Asset ist im CSV nicht
    belegt -> Standardannahme (Phase 7.1), nur bei Neuanlage."""
    system = session.execute(
        select(System).where(System.name == system_name)
    ).scalar_one_or_none()
    if system is None:
        prefix, timeframe = split_name(system_name)
        system = System(
            name=system_name,
            prefix=prefix,
            timeframe=timeframe,
            asset=resolve_asset(None, context=f"csv:{system_name}"),
            import_status="complete",
        )
        session.add(system)
    # Existing systems: no field changes, only trades are
    # im Aufrufer ersetzt.
    session.flush()
    return system


def run_csv_import(
    session: Session,
    filename: str,
    data: bytes,
    system_name: str,
    replace: bool = True,
) -> ImportRun:
    """Parse a Hadrian²-style CSV and persist its trades as ``source='auto'``.

    Upserts the target system by name (D3). With ``replace=True`` all existing
    ``source='auto'`` trades of that system are deleted before insert (D2, full
    mirror; manual trades are untouched). With ``replace=False`` the parsed
    trades are appended. Everything runs in a single transaction.
    """
    started_at = datetime.now(timezone.utc)
    try:
        trades, skipped = parse_csv(data)

        system = _upsert_system_by_name(session, system_name)

        if replace:
            session.execute(
                delete(Trade).where(
                    Trade.system_id == system.id, Trade.source == "auto"
                )
            )

        for p in trades:
            session.add(
                Trade(
                    system_id=system.id,
                    trade_datetime=p.trade_datetime,
                    zone=p.zone,
                    timeframe=p.timeframe,
                    entry=p.entry,
                    sl=p.sl,
                    exit=p.exit,
                    direction=p.direction,
                    r_value=p.r_value,
                    win_loss=p.win_loss,
                    source="auto",
                )
            )

        trades_imported = len(trades)
        tab_results = [
            {
                "tab": filename,
                "system_name": system_name,
                "status": "complete",
                "trades": trades_imported,
                "message": f"{skipped} rows skipped",
            }
        ]

        import_run = ImportRun(
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            file_path=filename,
            tabs_total=1,
            systems_complete=1,
            systems_incomplete=0,
            tabs_skipped=0,
            trades_imported=trades_imported,
            tab_results=tab_results,
        )
        session.add(import_run)
        session.commit()
        session.refresh(import_run)
        return import_run
    except Exception:
        session.rollback()
        raise


def _upsert_programmatic_system(
    session: Session, parsed: ParsedProgrammaticSystem
) -> System:
    """Upsert a programmatic system by name (D2).

    Sets ``provenance='programmatic'`` and ``source_engine``; ``prefix`` is
    derived from the name (1xx audit names) while ``timeframe`` comes from the
    source (Hadrian_Engine best-config TF; canonical M15/H1/H4 for Hadrian²),
    falling back to the name-derived segment. ``asset`` kommt aus der Quelle
    (Engine-Symbol / Hadrian²-Basismarkt), sonst Standardannahme (Phase 7.1). ``import_status`` is ``complete``
    iff at least one trade carries a numeric R, else ``incomplete``.
    """
    system = session.execute(
        select(System).where(System.name == parsed.name)
    ).scalar_one_or_none()
    if system is None:
        system = System(name=parsed.name)
        session.add(system)
        overrides: set[str] = set()
    else:
        # Field-level protection: fields overridden in the UI are left alone.
        overrides = set(system.user_overrides or [])

    prefix, name_tf = split_name(parsed.name)
    has_r = any(t.r_value is not None for t in parsed.trades)

    system.prefix = prefix
    if "timeframe" not in overrides:
        system.timeframe = parsed.timeframe or name_tf
    if "asset" not in overrides:
        system.asset = resolve_asset(
            parsed.asset, context=f"{parsed.source_engine}:{parsed.name}"
        )
    if "entry_rule" not in overrides:
        system.entry_rule = parsed.entry_rule
    if "sl_rule" not in overrides:
        system.sl_rule = parsed.sl_rule
    if "tp_rule" not in overrides:
        system.tp_rule = parsed.tp_rule
    if "notes" not in overrides:
        system.notes = parsed.notes
    system.reported_metrics = parsed.reported_metrics
    system.provenance = "programmatic"
    system.source_engine = parsed.source_engine
    system.import_status = "complete" if has_r else "incomplete"

    session.flush()
    return system


def _replace_auto_trades(
    session: Session, system: System, parsed: list[ParsedTrade]
) -> int:
    # Full mirror of source='auto' trades (D2); manual trades are untouched.
    session.execute(
        delete(Trade).where(Trade.system_id == system.id, Trade.source == "auto")
    )
    for p in parsed:
        session.add(
            Trade(
                system_id=system.id,
                trade_datetime=p.trade_datetime,
                zone=p.zone,
                timeframe=p.timeframe,
                entry=p.entry,
                sl=p.sl,
                exit=p.exit,
                direction=p.direction,
                r_value=p.r_value,
                win_loss=p.win_loss,
                source="auto",
            )
        )
    return len(parsed)


def _replace_sweeps(
    session: Session, system: System, parsed: list
) -> int:
    # Full mirror of the system's parameter_sweeps rows (D2/D3).
    session.execute(
        delete(ParameterSweep).where(ParameterSweep.system_id == system.id)
    )
    for s in parsed:
        session.add(
            ParameterSweep(
                system_id=system.id,
                label=s.label,
                param_x=s.param_x,
                param_y=s.param_y,
                metric=s.metric,
                points=s.points,
            )
        )
    return len(parsed)


def run_programmatic_import(
    session: Session, hadrian2_dir: str, engine_dir: str
) -> ImportRun:
    """Import both programmatic backtest sources into Postgres (Phase 5, T4/D2).

    Runs the two pure parsers (``parse_hadrian2`` / ``parse_hadrian_engine``),
    then upserts each system by name: full replacement of its ``source='auto'``
    trades AND of its ``parameter_sweeps`` rows. Manual (xlsx) systems/trades are
    never touched. A missing source directory is logged as a skipped tab and
    otherwise ignored. Everything runs in one transaction; rollback + re-raise on
    error (the API turns that into a 500).
    """
    started_at = datetime.now(timezone.utc)
    try:
        systems_complete = 0
        systems_incomplete = 0
        tabs_skipped = 0
        trades_imported = 0
        tabs_total = 0
        tab_results: list[dict] = []

        sources = (
            ("hadrian2", hadrian2_dir, parse_hadrian2),
            ("hadrian_engine", engine_dir, parse_hadrian_engine),
        )

        for source_engine, directory, parser in sources:
            if not directory or not os.path.isdir(directory):
                tabs_skipped += 1
                tab_results.append(
                    {
                        "tab": f"{source_engine}:{directory}",
                        "system_name": None,
                        "status": "skipped",
                        "trades": 0,
                        "message": f"source directory not found: {directory}",
                    }
                )
                continue

            for parsed in parser(directory):
                tabs_total += 1

                if parsed.parse_status == "skipped":
                    tabs_skipped += 1
                    tab_results.append(
                        {
                            "tab": f"{source_engine}:{parsed.name}",
                            "system_name": parsed.name,
                            "status": "skipped",
                            "trades": 0,
                            "message": parsed.message,
                        }
                    )
                    continue

                # Re-Import-Schutz (Phase 6, D1): UI-Systeme komplett unangetastet.
                existing = session.execute(
                    select(System).where(System.name == parsed.name)
                ).scalar_one_or_none()
                if existing is not None and existing.origin == "ui":
                    tabs_skipped += 1
                    tab_results.append(
                        {
                            "tab": f"{source_engine}:{parsed.name}",
                            "system_name": parsed.name,
                            "status": "skipped",
                            "trades": 0,
                            "message": "protected: origin=ui",
                        }
                    )
                    continue

                system = _upsert_programmatic_system(session, parsed)
                n = _replace_auto_trades(session, system, parsed.trades)
                _replace_sweeps(session, system, parsed.sweeps)
                trades_imported += n

                if system.import_status == "complete":
                    systems_complete += 1
                else:
                    systems_incomplete += 1

                tab_results.append(
                    {
                        "tab": f"{source_engine}:{parsed.name}",
                        "system_name": parsed.name,
                        "status": system.import_status,
                        "trades": n,
                        "message": parsed.message,
                    }
                )

        import_run = ImportRun(
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            file_path=f"hadrian2:{hadrian2_dir}; hadrian_engine:{engine_dir}",
            tabs_total=tabs_total,
            systems_complete=systems_complete,
            systems_incomplete=systems_incomplete,
            tabs_skipped=tabs_skipped,
            trades_imported=trades_imported,
            tab_results=tab_results,
        )
        session.add(import_run)
        session.commit()
        session.refresh(import_run)
        return import_run
    except Exception:
        session.rollback()
        raise
