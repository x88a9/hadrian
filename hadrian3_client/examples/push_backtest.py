"""Example: push an EMA demo backtest to a running Hadrian3 API.

Requires the [pandas] extra (this is the ONLY place pandas is used — the
library itself never imports it):

    pip install -e ".[pandas]"

Run against a live API:

    API_URL=http://127.0.0.1:8000 python examples/push_backtest.py

It creates the demo system, bulk-imports the CSV trades (idempotent replace),
then prints the computed all/oos metrics for the system.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pandas as pd

from hadrian3_client import Client

SYSTEM_NAME = "EMA-M1-900.demo"
CSV_PATH = Path(__file__).parent / "example_trades.csv"


def main() -> None:
    api_url = os.environ.get("API_URL", "http://127.0.0.1:8000")
    client = Client(api_url)

    print(f"Creating system {SYSTEM_NAME!r} at {api_url} ...")
    client.create_system(
        SYSTEM_NAME,
        entry_rule="Demo: EMA-Cross Backtest-Push",
        sl_rule="Demo",
        tp_rule="Demo",
    )

    print(f"Bulk-importing trades from {CSV_PATH.name} ...")
    df = pd.read_csv(CSV_PATH)
    run = client.bulk_import(df, SYSTEM_NAME)
    print(
        "  import run:",
        {
            "trades_imported": run.get("trades_imported"),
            "systems_complete": run.get("systems_complete"),
            "systems_incomplete": run.get("systems_incomplete"),
        },
    )

    # Fetch metrics: GET /systems and filter by name (D-shape from contract).
    resp = httpx.get(f"{api_url.rstrip('/')}/systems", timeout=30.0)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    system = next((s for s in items if s.get("name") == SYSTEM_NAME), None)
    if system is None:
        print(f"System {SYSTEM_NAME!r} not found in /systems response.")
        return

    metrics = system.get("metrics", {})
    all_m = metrics.get("all") or {}
    oos_m = metrics.get("oos") or {}
    print(f"\nMetrics for {SYSTEM_NAME}:")
    print(
        "  ALL  ->",
        f"trades={all_m.get('total_trades')}",
        f"ev={all_m.get('ev')}",
        f"composite_grade={all_m.get('composite_grade')}",
    )
    print(
        "  OOS  ->",
        f"trades={oos_m.get('total_trades')}",
        f"ev={oos_m.get('ev')}",
        f"composite_grade={oos_m.get('composite_grade')}",
    )


if __name__ == "__main__":
    main()
