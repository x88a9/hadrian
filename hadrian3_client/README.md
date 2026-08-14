# hadrian3-client

Python client for the Hadrian³ REST API. Create systems, log individual trades
and push whole backtests (CSV or pandas DataFrame).

`httpx` is the only hard dependency. The library **never** imports `pandas` —
DataFrames are duck-typed through their `.to_csv()` method. The `[pandas]` extra
is pure convenience for examples and scripts.

## Installation

```bash
# from the client directory (recommended)
pip install -e .

# with the pandas extra (only needed for examples/push_backtest.py)
pip install -e ".[pandas]"
```

> Note: when running `pip install -e ./hadrian3_client` from the repository root,
> pass `--config-settings editable_mode=compat`. The project folder and the
> package share the name `hadrian3_client`; without `compat`, the sibling folder
> of the same name shadows the installed package on `sys.path` as a namespace
> package. `compat` puts the project directory on `sys.path` so the regular
> package wins.

## Quickstart

```python
from datetime import datetime
from hadrian3_client import Client, Hadrian3ClientError

client = Client("http://127.0.0.1:8000")

# 1. Create a system (idempotent upsert by name)
client.create_system(
    "EMA-M1-900.demo",
    entry_rule="EMA cross long/short",
    sl_rule="swing low",
    tp_rule="2R",
)

# 2. Log a single trade (append-only; source='auto' is set server-side)
client.log_trade(
    system_name="EMA-M1-900.demo",
    trade_datetime=datetime(2024, 3, 4, 15, 0),
    direction="long",
    entry=64123.5, sl=63900.0, exit=64800.0,
    r_value=2.1,
)

# 3. Push a whole backtest via CSV/DataFrame (idempotent, see below)
import pandas as pd
df = pd.read_csv("trades.csv")
run = client.bulk_import(df, "EMA-M1-900.demo", replace=True)
print(run["trades_imported"])

# Errors carry status_code and detail
try:
    client.log_trade(system_name="unknown", r_value=1.0)
except Hadrian3ClientError as e:
    print(e.status_code, e.detail)
```

## Method reference

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `Client(api_url="http://127.0.0.1:8000", timeout=30.0, http_client=None)` | – | `http_client` is injectable (`httpx.MockTransport` / `ASGITransport`). |
| `create_system(name, *, entry_rule=None, sl_rule=None, tp_rule=None, notes=None, status=None)` | `POST /systems` | Idempotent upsert by name; only non-`None` fields are sent. |
| `log_trade(*, system_name=None, system_id=None, r_value=None, trade_datetime=None, direction=None, entry=None, sl=None, exit=None, zone=None, timeframe=None, win_loss=None)` | `POST /trades` | Append-only single trade; `datetime`/`date` → ISO-8601. `system_id` XOR `system_name`. |
| `bulk_import(df, system_name, replace=True)` | `POST /import/csv` | Multipart CSV import. `df`: DataFrame-like (`.to_csv`), `bytes`, a CSV `str` or a file path. |

`bulk_import` accepts, for `df`:

- **DataFrame-like** (has `.to_csv`): `df.to_csv(index=False)` is called.
- **`bytes`**: used directly as the CSV payload.
- **`str` / `os.PathLike`**: if the value points at an **existing file** the file
  is read; otherwise the string is treated as **raw CSV content**.

## CSV column contract

The server maps CSV columns onto the trade model as follows:

| CSV column | → Trade field | Note |
| --- | --- | --- |
| `entry_time` | `trade_datetime` | ISO-8601; empty → no date |
| `direction` | `direction` | `long`/`short` (buy/sell are normalised) |
| `entry_price` | `entry` | |
| `sl_price` | `sl` | |
| `exit_price` | `exit` | |
| `net_r` | `r_value` | **net of costs** — this is what the metrics are built on |
| `win_loss` | `win_loss` | used when present, otherwise derived from `r_value` |
| `timeframe` | `timeframe` | optional |
| `exit_time` | — | **discarded** |
| `tp_price` | — | **discarded** |
| `exit_reason` | — | **discarded** |
| `gross_r` | — | **discarded** (only `net_r` counts) |
| _any other column_ | — | **discarded** |

`NaN` and error strings become `None`. Rows with no parseable field are skipped
and counted. A CSV with no recognised column at all returns `400`.

## Idempotency

- `bulk_import(..., replace=True)` (the default) is the **idempotent** path: the
  server deletes all `source='auto'` trades of that system before inserting,
  mirroring the wholesale-replacement semantics of the xlsx import. Manually
  imported trades are untouched.
- `log_trade` is deliberately **append-only** — a single trade has no stable
  natural key, so there is no deduplication. Use `bulk_import` for repeatable
  runs.

See `docs/DECISIONS.md`, "Client library has no pandas dependency", for the
reasoning behind both.

## Example run

```bash
pip install -e ".[pandas]"
API_URL=http://127.0.0.1:8000 python examples/push_backtest.py
```

`examples/example_trades.csv` holds about a dozen rows in the full upstream
format (IS 2023 plus OOS 2024/2025), including one deliberately broken row that
the importer skips.
