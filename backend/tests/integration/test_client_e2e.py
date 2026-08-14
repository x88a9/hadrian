"""End-to-end test: the real ``hadrian3_client`` -> FastAPI app -> Postgres.

This exercises the full stack as a user of the pip client would (D6): the actual
client library drives requests through ``httpx.ASGITransport`` straight into the
FastAPI app, whose ``get_db`` dependency is overridden onto the per-test Postgres
session (same wiring pattern as ``test_api.py``). No network, no mocks.

The fixture data is ``hadrian3_client/examples/example_trades.csv``; every
expected number is derived from that file in :func:`_expected_from_csv` so the
test stays an independent oracle (it does not call the backend parser).

Auto-skipped when the Postgres server (conftest) or the example CSV is missing.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from statistics import mean

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import get_db
from app.main import app

from hadrian3_client import Client

pytestmark = pytest.mark.integration

# repo root: .../backend/tests/integration/<this file>
REPO_ROOT = Path(__file__).resolve().parents[3]
CSV_PATH = REPO_ROOT / "hadrian3_client" / "examples" / "example_trades.csv"
DEMO_SYSTEM = "EMA-M1-900.demo"
SPLIT_DATE = date(2024, 1, 1)  # IS < 2024-01-01 <= OOS (D "IS/OOS-Split")


def _expected_from_csv(path: Path) -> dict:
    """Derive the ground-truth numbers straight from the CSV, mirroring the
    importer's semantics (D5) independently:

    * A row is *imported* as a trade unless every mapped target field is empty.
      NB: the last row carries only ``entry_time`` -> it is NOT skipped, it is
      imported with ``entry=None``/``r_value=None``. Hence ``imported`` == 12,
      not 11 (the "broken" row is a datetime-only row, not an all-empty row).
    * ``total_trades`` counts rows with a numeric ``entry_price`` (xlsx COUNT
      rule ported to the metrics layer) -> the datetime-only row is excluded.
    * ``ev`` = mean of the numeric ``net_r`` values (NET R, not gross).
    """
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))

    imported = 0
    total_trades = 0
    is_count = 0
    oos_count = 0
    net_rs: list[float] = []
    r_sequence: list[float | None] = []  # per imported row, chronological

    for row in rows:
        entry_time = row["entry_time"].strip()
        entry_price = row["entry_price"].strip()
        net_r = row["net_r"].strip()
        mapped = [
            entry_time,
            row["direction"].strip(),
            entry_price,
            row["sl_price"].strip(),
            row["exit_price"].strip(),
            net_r,
        ]
        if not any(mapped):
            continue  # all-empty row would be skipped by the parser

        imported += 1
        r_value = float(net_r) if net_r else None
        r_sequence.append(r_value)
        if net_r:
            net_rs.append(float(net_r))
        if entry_price:
            total_trades += 1
            d = datetime.fromisoformat(entry_time).date()
            if d < SPLIT_DATE:
                is_count += 1
            else:
                oos_count += 1

    return {
        "imported": imported,
        "total_trades": total_trades,
        "is_count": is_count,
        "oos_count": oos_count,
        "ev": mean(net_rs),
        "r_sequence": r_sequence,
    }


@pytest.fixture()
def e2e(db_session):
    """Wire the FastAPI app onto the test session and expose (raw httpx, Client).

    ``get_db`` is overridden onto the same ``db_session`` every endpoint call
    shares (each endpoint commits on it). Requests are dispatched in-process via
    Starlette's ``TestClient`` -- an ``httpx.Client`` subclass that drives an
    ``ASGITransport`` against the app through a sync portal (a bare
    ``httpx.Client(transport=ASGITransport(...))`` can't, since ASGITransport is
    async-only). We inject that same client into the real ``hadrian3_client``.
    ``base_url`` only shapes relative URLs; the transport routes to the app
    regardless of host.
    """
    if not CSV_PATH.is_file():
        pytest.skip(f"example CSV missing at {CSV_PATH}")

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app, base_url="http://test") as raw:
            client = Client(api_url="http://test", http_client=raw)
            yield raw, client
    finally:
        app.dependency_overrides.clear()


def _auto_trades(raw: httpx.Client, system_id: int) -> dict:
    res = raw.get("/trades", params={"source": "auto", "system_id": system_id})
    assert res.status_code == 200
    return res.json()


def test_client_to_api_to_db_roundtrip(e2e):
    raw, client = e2e
    exp = _expected_from_csv(CSV_PATH)

    # 1) create the demo system via the real client ----------------------------
    system = client.create_system(
        DEMO_SYSTEM,
        entry_rule="Demo",
        sl_rule="Demo",
        tp_rule="Demo",
    )
    system_id = system["id"]
    assert isinstance(system_id, int)
    assert system["prefix"] == "EMA"
    assert system["timeframe"] == "M1"
    assert system["entry_rule"] == "Demo"

    # 2) bulk import the example CSV (auto trades) -----------------------------
    run = client.bulk_import(CSV_PATH, DEMO_SYSTEM)
    # ImportRun counts every imported row; the datetime-only last row IS imported
    # (only genuinely all-empty rows are skipped) -> 12, not 11.
    assert run["trades_imported"] == exp["imported"] == 12
    assert run["tabs_total"] == 1

    # 3) GET /systems: demo present with the metrics computed from the CSV ------
    listing = raw.get("/systems").json()
    demo = next(i for i in listing["items"] if i["name"] == DEMO_SYSTEM)
    m = demo["metrics"]
    # total_trades counts rows with a numeric entry -> excludes the datetime-only
    # row, so 11 even though 12 trade rows exist.
    assert m["all"]["total_trades"] == exp["total_trades"] == 11
    assert m["all"]["ev"] == pytest.approx(exp["ev"], rel=1e-9)
    # IS/OOS split partitions the dated, entry-bearing trades (5 in 2023, 6 from
    # 2024 on) and their counts add back up to the total.
    assert m["is"]["total_trades"] == exp["is_count"] == 5
    assert m["oos"]["total_trades"] == exp["oos_count"] == 6
    assert m["is"]["total_trades"] + m["oos"]["total_trades"] == m["all"]["total_trades"]

    # 4) GET /trades?source=auto: all auto, r_value == NET r (not gross) --------
    auto = _auto_trades(raw, system_id)
    assert auto["total"] == exp["imported"] == 12
    assert all(t["source"] == "auto" for t in auto["items"])
    # default order=asc -> chronological, matching the CSV row order.
    actual_rs = [t["r_value"] for t in auto["items"]]
    assert len(actual_rs) == len(exp["r_sequence"])
    for got, want in zip(actual_rs, exp["r_sequence"]):
        if want is None:
            assert got is None
        else:
            assert got == pytest.approx(want, rel=1e-9)
    # spot-check the first trade is the NET value (1.92), never the gross (2.0).
    assert actual_rs[0] == pytest.approx(1.92, rel=1e-9)

    # 5) log_trade appends exactly one auto trade ------------------------------
    logged = client.log_trade(
        system_name=DEMO_SYSTEM,
        r_value=1.5,
        trade_datetime=datetime(2025, 1, 1, 12, 0),
    )
    assert logged["source"] == "auto"
    assert logged["r_value"] == pytest.approx(1.5)
    after_log = _auto_trades(raw, system_id)
    assert after_log["total"] == exp["imported"] + 1 == 13  # trade rows +1
    # (metrics.all.total_trades stays 11: log_trade sent no entry price, and
    #  total_trades counts entry-bearing rows only -- documented, not asserted-on.)

    # 6) re-import with replace=True is idempotent -----------------------------
    rerun = client.bulk_import(CSV_PATH, DEMO_SYSTEM, replace=True)
    assert rerun["trades_imported"] == exp["imported"] == 12
    after_replace = _auto_trades(raw, system_id)
    # replace=True mirrors the file: it drops ALL source='auto' trades first, so
    # the step-5 logged trade (also source='auto') is replaced too (D2 semantics).
    assert after_replace["total"] == exp["imported"] == 12

    # 7) an xlsx import must not touch the demo system or its auto trades -------
    if Path(settings.XLSX_PATH).is_file():
        xlsx = raw.post("/import/xlsx")
        assert xlsx.status_code == 200
        # demo system still present...
        listing2 = raw.get("/systems").json()
        assert any(i["name"] == DEMO_SYSTEM for i in listing2["items"])
        # ...and its auto trades are untouched (xlsx only replaces manual trades).
        still = _auto_trades(raw, system_id)
        assert still["total"] == exp["imported"] == 12
