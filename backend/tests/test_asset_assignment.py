"""Tests for asset derivation (``systems.asset``).

Three levels:

1. **Unit** — normalisation and classification in ``app/importers/assets.py``:
   strip suffixes, never read a timeframe as an asset, carry an unknown ticker
   through unchanged, fall back to BTC without evidence.
2. **Re-import protection** — when ``asset`` sits in ``systems.user_overrides``
   the import leaves the field alone. Needs Postgres; skipped without a server.
3. **Real sources** — a handful of verified cases against the original files,
   skipped cleanly when those files are not available.
"""

from __future__ import annotations

import json
import os

import pytest

from app.importers.assets import (
    DEFAULT_ASSET,
    HADRIAN2_BASE_ASSET,
    asset_candidate_from_cell,
    derive_asset_from_symbol,
    derive_asset_from_timeframe_cells,
    is_known,
    normalize_ticker,
    resolve_asset,
)

from tests.paths import ENGINE_DIR, REAL_XLSX, SAMPLE_XLSX, has_real_xlsx

_XLSX = str(REAL_XLSX if has_real_xlsx() else SAMPLE_XLSX)
_ENGINE = ENGINE_DIR


# --------------------------------------------------------------------------- #
# 1) Normalisierung
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("BTCUSDT.P", "BTC"),
        ("BTCUSDT", "BTC"),
        ("ETHUSDT.P", "ETH"),
        ("BTCUSD", "BTC"),
        ("BTC-PERP", "BTC"),
        ("BINANCE:BTCUSDT.P", "BTC"),
        ("btcusdt.p", "BTC"),
        ("XMR", "XMR"),
        ("  DOT  ", "DOT"),
        ("SOL", "SOL"),
    ],
)
def test_normalize_ticker(raw, expected):
    assert normalize_ticker(raw) == expected


def test_normalize_ticker_keeps_trailing_p_of_real_tickers():
    # "XRP" must not be misread as carrying a perp suffix.
    assert normalize_ticker("XRP") == "XRP"
    assert normalize_ticker("XRPUSDT.P") == "XRP"


def test_normalize_ticker_rejects_non_tickers():
    assert normalize_ticker(None) is None
    assert normalize_ticker("") is None
    assert normalize_ticker("   ") is None


def test_unknown_ticker_is_taken_as_is_and_not_mapped_to_btc():
    assert normalize_ticker("PEPEUSDT.P") == "PEPE"
    assert derive_asset_from_symbol("PEPEUSDT.P") == "PEPE"
    assert is_known("PEPE") is False
    assert is_known("BTC") is True


# --------------------------------------------------------------------------- #
# 2) Mehrdeutige xlsx-"Timeframe"-Spalte
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw", ["BTC", "XMR", "DOT", "BTCUSDT.P"])
def test_timeframe_cell_recognized_as_asset(raw):
    assert asset_candidate_from_cell(raw) is not None


@pytest.mark.parametrize(
    "raw",
    [
        "H1", "H4", "M15", "M5", "M1", "D", "W",
        "D / H1", "W / H4", "00:15:00", "U.S./New York",
        "Asia", "London", "New York", "Daily", None, "", "   ",
    ],
)
def test_timeframe_cell_not_mistaken_for_asset(raw):
    assert asset_candidate_from_cell(raw) is None


def test_derive_from_cells_majority_and_empty():
    assert derive_asset_from_timeframe_cells(["H1", "H1", None]) is None
    assert derive_asset_from_timeframe_cells(["BTC", "BTC", None]) == "BTC"
    # Mixed input: the most frequent ticker wins, and the ambiguity is logged.
    assert derive_asset_from_timeframe_cells(["DOT", "BTC", "DOT"]) == "DOT"


# --------------------------------------------------------------------------- #
# 3) Default ohne Beleg
# --------------------------------------------------------------------------- #
def test_resolve_asset_defaults_to_btc():
    assert resolve_asset(None) == DEFAULT_ASSET == "BTC"
    assert resolve_asset("") == "BTC"
    assert resolve_asset("DOT") == "DOT"
    assert HADRIAN2_BASE_ASSET == "BTC"


# --------------------------------------------------------------------------- #
# 4) Echte Quellen (Auto-Skip)
# --------------------------------------------------------------------------- #
# Real-source checks are data-driven: the expected asset per system lives in a
# JSON file outside the repository, pointed at by HADRIAN3_ASSET_EXPECTATIONS.
# That keeps the checks available on a machine that has the private sources
# without shipping any system identifier here.
#
#   {"xlsx": {"<system>": "XMR", "<system>": null}, "engine": {"<system>": "AVAX"}}
_EXPECTATIONS = os.environ.get("HADRIAN3_ASSET_EXPECTATIONS", "")


def _expectations(section: str) -> dict:
    if not _EXPECTATIONS or not os.path.isfile(_EXPECTATIONS):
        return {}
    with open(_EXPECTATIONS, encoding="utf-8") as fh:
        return json.load(fh).get(section, {})


@pytest.mark.skipif(
    not (has_real_xlsx() and _expectations("xlsx")),
    reason="needs the private workbook and HADRIAN3_ASSET_EXPECTATIONS",
)
def test_real_xlsx_assets():
    from app.importers.xlsx import parse_workbook

    by_name = {t.system_name: t for t in parse_workbook(_XLSX).tabs}
    for system, expected in _expectations("xlsx").items():
        assert system in by_name, f"{system} not found in workbook"
        assert by_name[system].asset == expected, system


@pytest.mark.skipif(
    not (_ENGINE and os.path.isdir(_ENGINE) and _expectations("engine")),
    reason="needs HADRIAN_ENGINE_RESULTS_DIR and HADRIAN3_ASSET_EXPECTATIONS",
)
def test_real_engine_assets():
    from app.importers.hadrian_engine import parse_hadrian_engine

    by_name = {s.name: s for s in parse_hadrian_engine(_ENGINE)}
    for system, expected in _expectations("engine").items():
        assert system in by_name, f"{system} not found in engine results"
        assert by_name[system].asset == expected, system

    # Whatever the expectations cover, every parsed system must resolve an asset.
    assert all(s.asset for s in by_name.values() if s.parse_status != "skipped")


# --------------------------------------------------------------------------- #
# 5) Re-import protection (needs Postgres -> auto-skip)
# --------------------------------------------------------------------------- #
@pytest.mark.integration
def test_user_override_asset_survives_xlsx_reimport(db_session, monkeypatch):
    from sqlalchemy import select

    from app.importers.xlsx import ParsedTab, ParsedTrade, ParseResult
    from app.models import System
    from app.services.import_service import run_xlsx_import

    db_session.add(
        System(
            name="B-H1-777",
            asset="DOT",
            user_overrides=["asset"],
            import_status="complete",
        )
    )
    db_session.commit()

    def fake_parse_workbook(path):  # noqa: ARG001
        return ParseResult(
            tabs=[
                ParsedTab(
                    tab_name="B-H1-777",
                    system_name="B-H1-777",
                    asset="BTC",
                    trades=[ParsedTrade(entry=1.0, r_value=1.0, win_loss="win")],
                    parse_status="complete",
                )
            ]
        )

    monkeypatch.setattr(
        "app.services.import_service.parse_workbook", fake_parse_workbook
    )
    run_xlsx_import(db_session, "dummy.xlsx")

    system = db_session.execute(
        select(System).where(System.name == "B-H1-777")
    ).scalar_one()
    assert system.asset == "DOT"  # UI-Wert bleibt


@pytest.mark.integration
def test_backfill_script_only_fills_null_assets(db_session):
    """backfill_assets.py only fills missing assets, and only writes with --apply."""
    import importlib.util

    from sqlalchemy import select

    from app.models import System

    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts",
        "backfill_assets.py",
    )
    spec = importlib.util.spec_from_file_location("backfill_assets", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    db_session.add_all(
        [
            System(name="MR-M3-800", import_status="complete"),          # NULL
            System(name="B-H1-800", import_status="complete"),           # NULL, kein Beleg
            System(name="UI-800", asset="DOT", import_status="complete"),  # gesetzt
        ]
    )
    db_session.commit()

    evidence = {"MR-M3-800": "XMR", "UI-800": "SOL"}

    # dry-run schreibt nicht
    _dist, changes, _defaulted = module.backfill(db_session, evidence, False)
    assert {name for name, _ in changes} == {"MR-M3-800", "B-H1-800"}
    assert db_session.execute(
        select(System.asset).where(System.name == "MR-M3-800")
    ).scalar_one() is None

    dist, changes, defaulted = module.backfill(db_session, evidence, True)
    assets = dict(db_session.execute(select(System.name, System.asset)).all())
    assert assets == {
        "MR-M3-800": "XMR",
        "B-H1-800": DEFAULT_ASSET,
        "UI-800": "DOT",  # bestehende Zuordnung bleibt, trotz abweichendem Beleg
    }
    assert defaulted == ["B-H1-800"]
    assert dist == {"BTC": 1, "XMR": 1, "DOT": 1}

    # idempotent: zweiter Lauf aendert nichts mehr
    _dist2, changes2, _def2 = module.backfill(db_session, evidence, True)
    assert changes2 == []


@pytest.mark.integration
def test_import_sets_asset_and_falls_back_to_default(db_session, monkeypatch):
    from sqlalchemy import select

    from app.importers.programmatic_types import ParsedProgrammaticSystem
    from app.importers.xlsx import ParsedTab, ParsedTrade, ParseResult
    from app.models import System
    from app.services.import_service import run_programmatic_import, run_xlsx_import

    def fake_parse_workbook(path):  # noqa: ARG001
        return ParseResult(
            tabs=[
                ParsedTab(
                    tab_name="MR-M3-900",
                    system_name="MR-M3-900",
                    asset="XMR",
                    trades=[ParsedTrade(entry=1.0, r_value=1.0, win_loss="win")],
                    parse_status="complete",
                ),
                ParsedTab(
                    tab_name="B-H1-900",
                    system_name="B-H1-900",
                    asset=None,  # kein Beleg
                    trades=[ParsedTrade(entry=1.0, r_value=1.0, win_loss="win")],
                    parse_status="complete",
                ),
            ]
        )

    def fake_engine(directory):  # noqa: ARG001
        return [
            ParsedProgrammaticSystem(
                name="prog-900",
                source_engine="hadrian_engine",
                asset="SOL",
                parse_status="incomplete",
            )
        ]

    monkeypatch.setattr(
        "app.services.import_service.parse_workbook", fake_parse_workbook
    )
    monkeypatch.setattr("app.services.import_service.parse_hadrian2", lambda d: [])
    monkeypatch.setattr(
        "app.services.import_service.parse_hadrian_engine", fake_engine
    )

    run_xlsx_import(db_session, "dummy.xlsx")
    run_programmatic_import(db_session, os.getcwd(), os.getcwd())

    assets = dict(
        db_session.execute(select(System.name, System.asset)).all()
    )
    assert assets["MR-M3-900"] == "XMR"
    assert assets["B-H1-900"] == DEFAULT_ASSET  # dokumentierte Standardannahme
    assert assets["prog-900"] == "SOL"
