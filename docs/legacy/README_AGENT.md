# README_AGENT.md — Hadrian Engine Onboarding

**Read this file in full before doing anything else.**

**ENGINE VERSION:** Rebuilt 2026-05-14. All 7 architectural flaws fixed. Prior results validated as reproducible within <1%.

---

## 1. WHAT THIS IS

The Hadrian Engine is a modular backtesting framework for systematic BTC/ETH trading research. It is designed to produce statistically honest, reproducible results with hard-coded protection against the most common backtesting fallacies.

Core principles:
- **One system file = one trading concept.** All signal logic lives in `systems/<name>.py`. Nothing else.
- **The core engine never changes.** `core/engine.py`, `core/metrics.py`, `core/exports.py`, and `core/data_loader.py` are infrastructure — never edit them.
- **All research is logged and never overwritten.** Every run appends to `results.xlsx` and creates a new `backtest_N.xlsx`. There is no delete or overwrite mechanism.

---

## 2. BEFORE YOU DO ANYTHING

Do these steps in order. Do not skip any.

1. Read this file in full.
2. Read `config.env` — understand the fee model and IS/OOS date split.
3. Read `core/engine.py` — understand the signal contract and the six anti-fallacy rules. These are non-negotiable.
4. Run `ls systems/` and read the docstring at the top of every `.py` file found. That is your system inventory.
5. Run `ls results/` and open `results.xlsx` in every subfolder. Understand what has already been tested. **Do not re-run a config that is already logged unless explicitly instructed.**

---

## 3. FILE ROLES

| File | Role | Editable? |
|------|------|-----------|
| `config.env` | Fees, IS/OOS dates, defaults | Yes — only when switching exchange or date windows |
| `core/data_loader.py` | Fetches and caches OHLCV from Binance | **Never** |
| `core/engine.py` | Runs all backtests, enforces anti-fallacy rules | **Never** |
| `core/metrics.py` | Computes statistics | **Never** |
| `core/exports.py` | Writes all output files | **Never** |
| `core/config_loader.py` | Parses config.env | **Never** |
| `systems/<name>.py` | Signal logic only | Yes — this is the only file you write or edit |
| `run_backtest.py` | CLI entry point | **Never** |
| `results/<system>/results.xlsx` | Master ledger | **Never manually edit** |
| `results/<system>/backtest_N.xlsx` | Trade log per run | **Never manually edit** |

---

## 4. SIGNAL CONTRACT (UPDATED — ENGINE REBUILD)

Every system file must export exactly one function with this exact signature:

```python
def get_signals(dfs: dict[str, pd.DataFrame], params: dict, state: dict, i: int) -> list[dict]:
```

For **backward compatibility**, single-TF systems may still use the old signature:

```python
def get_signals(df: pd.DataFrame, params: dict) -> list[dict]:
```

The engine auto-detects which signature your system uses.

### New-style (multi-TF) parameters:
- `dfs` — dict mapping TF string (e.g. `"1d"`, `"1h"`) to DataFrame slice ending at the current bar
- `params` — JSON-decoded dict from CLI `--params`
- `state` — persistent dict created once per run; read/write freely; engine never touches it
- `i` — current bar index on the **entry TF**

### Signal dict keys:

```python
{
    "signal_time": datetime,        # close time of the signal candle
    "entry_price": float,           # proposed entry price (reference)
    "sl_price": float,              # stop loss price
    "tp_price": float | None,       # take profit price, or None for managed exit
    "direction": "long" | "short",
    "entry_type": "close" | "next_open" | "limit",
    "label": str,                   # human-readable description
    # Optional:
    "limit_price": float,           # REQUIRED when entry_type="limit"
    "limit_expiry_bars": int,       # default 5; how many bars to wait for fill
    "risk_fraction": float,         # default 1.0; scales R (0.5 = half-sized)
}
```

### Optional dynamic exit callback:

```python
def should_exit(df_slice: pd.DataFrame, open_trade: dict, state: dict) -> dict | None:
```

- Called on **every bar** while a trade is open, **before** SL/TP checks
- Return `None` to stay in the trade
- Return `{"exit_price": float, "exit_reason": str}` to close at that price
- `open_trade` contains: `entry_time`, `entry_price`, `sl_price`, `tp_price`, `direction`, `label`, `bars_open`, `state`

### Exit check order per bar:
1. `should_exit()` callback (if defined by the system)
2. SL hit (`low <= sl_price` for longs, `high >= sl_price` for shorts)
3. TP hit (`high >= tp_price` for longs, `low <= tp_price` for shorts)
4. End of data

---

## 5. MULTI-TIMEFRAME USAGE

Use `--signal_tf` and `--entry_tf` as separate arguments:

```bash
python run_backtest.py --system trend_dh1_001 --config "MaxRYear" --signal_tf 1d --entry_tf 1h --mode full
```

If only `--tf` is passed, it is used for both signal and entry.

**Alignment guarantee:** At bar `i` on the entry TF, `dfs["1d"]` contains only daily bars whose close time is `<=` the current entry bar's close time. No future daily data is ever visible.

---

## 6. STATE DICT

The engine creates `state = {}` once per backtest run.
- Passed to `get_signals` and `should_exit` on every bar
- The system can read and write any keys freely
- The engine never reads or modifies `state` — it only passes the reference through
- `state` is reset to `{}` at the start of each new backtest run
- `state` is NOT persisted between runs

Use `state` to track things like:
- Consolidation box construction
- Retest counts
- Signal windows (e.g. "in entry window for 5 more bars")
- Any other persistent state machine data

---

## 7. LIMIT ORDERS

Set `entry_type="limit"` and include `limit_price` in the signal dict.

```python
{
    "entry_type": "limit",
    "limit_price": current_close * 0.995,
    "limit_expiry_bars": 3,  # optional, default 5
}
```

Engine behavior:
- Places a pending order at `limit_price`
- Each subsequent bar: if `low <= limit_price` (long) or `high >= limit_price` (short), fill at `limit_price`
- If `limit_expiry_bars` passes without fill: order is cancelled (no trade recorded)
- Only one pending order at a time (same as no-overlapping-trades rule)

---

## 8. HOW TO ADD A NEW SYSTEM

**Step 1.** Create `systems/<name>.py`.

**Step 2.** At the top of the file, write a docstring that describes:
- What the system trades (the market structure or setup it targets)
- What params it accepts and what each does
- Entry logic in plain English
- Stop loss logic in plain English
- Take profit / exit logic in plain English

**Step 3.** Export `get_signals()` with the correct signature.

**Step 4.** Optionally export `should_exit()` for dynamic exits.

**Step 5.** Run in-sample first:

```bash
python run_backtest.py --system <name> --config "<label>" --mode IS
```

**Rules for writing get_signals:**
- `dfs` (or `df`) is a slice ending at the signal candle. The last row is the current bar.
- **Never index forward.** Never use `df.shift(-1)`, negative `.iloc` indices, or any lookahead.
- Use only `df.iloc[-1]`, `df.iloc[:-1]`, indicator libraries, and past rows.
- Do not filter or trim the df based on date — the engine handles windowing.

---

## 9. ANTI-FALLACY CHECKLIST

Run this checklist before every backtest run. Log the result in your decision notes.

- [ ] **No lookahead:** signals use only `df.iloc[:i+1]` — the engine enforces this, but verify your system logic does not rely on future data in any indirect way
- [ ] **Entry timing:** entry is on signal candle close (`entry_type="close"`), next candle open (`entry_type="next_open"`), or limit fill (`entry_type="limit"`) — never mid-candle, never delayed by more than one bar
- [ ] **Fees applied:** loaded from `config.env` (`TAKER_FEE`), never hardcoded as 0
- [ ] **Sample size:** n ≥ 30 before drawing any conclusions — engine will warn if n < 30
- [ ] **IS first:** IS results exist before running OOS — engine will refuse OOS if no IS run is logged for the exact (system, config) pair
- [ ] **No parameter leakage:** no parameter was chosen by looking at OOS data, even informally
- [ ] **No overlapping trades:** engine enforces one position at a time, but verify your signal logic does not assume concurrent positions

### ML-specific rules (Phase 3 HMM research):
- [ ] HMM trained only on `df.iloc[:i]` to predict state at bar `i`
- [ ] Feature normalization uses rolling stats from training window only
- [ ] State labels realigned after every retrain
- [ ] No hyperparameter choices made by looking at OOS data
- [ ] State permutation function tested and confirmed working before first run

---

## 10. RESEARCH LOG PROTOCOL

- Every config variation = new run = new `backtest_N.xlsx` + new row in `results.xlsx`
- **Never overwrite any existing file.** The logging system is append-only by design.
- The `Notes` column in `results.xlsx` must explain *why* this config was tried
- If a research branch is abandoned, write `"DEAD END: <reason>"` in Notes for the last run of that branch
- The `results.xlsx` for each system is the source of truth. If it is not there, it was not tested.

---

## 11. SYSTEM INVENTORY

**Do not hardcode system names.** At the start of every session:

1. `ls systems/` — list all `.py` files (ignore `.gitkeep`)
2. Read the docstring at the top of each file
3. That is your current system inventory
4. Then `ls results/` and read `results.xlsx` in each folder to know what has already been run

---

## 12. HOW TO INTERPRET RESULTS

| Threshold | Meaning |
|-----------|---------|
| n < 30 | Not statistically meaningful — do not conclude anything |
| EV > 1.0R AND WR > 25% AND Sharpe > 0.8 AND OOS confirms IS | System has edge |
| EV > 0.5R, OOS not yet run | Borderline — run more IS configs first, then OOS |
| EV < 0.3R in IS | Dead end — abandon this concept |
| OOS significantly underperforms IS | Likely overfit — dead end |

**Benchmark reference:** The highest-EV system actually found in old_tools/ research is `mean_reversion_range.py` (sysfind1: ~2.4R EV on ETH 1h). The highest-EV "trend" system is `post_breakout_continuation.py` (sysfind3: ~2.0R EV on BTC 1h). The TREND-DH1-001 benchmark (5.06R EV) was an aspirational target from prompts, never achieved empirically. See ANALYSIS.md for full audit. Use 2.0–2.5R EV as a realistic baseline for viable systems.

When computing "significantly underperforms": if OOS EV < 50% of IS EV, treat it as a failed OOS.

---

## 13. CONTACT PROTOCOL

**Proceed autonomously when:**
- Results are clearly negative (EV < 0.3R in IS)
- n < 30 (log the warning and skip — do not draw conclusions)
- The next logical config variation is obvious from the IS results

**Stop and ask the user when:**
- A run produces borderline results (EV 0.3–1.0R) and you are unsure whether to continue exploring or move to OOS
- You are about to run OOS for the **first time** on any system
- You have caught a potential fallacy in existing code and need a decision on how to fix it
- You have exhausted IS exploration across multiple configs and need direction on what concept to try next
- Any result is anomalously good (EV > 5R) — verify the logic before proceeding

---

## 14. QUICK REFERENCE — CLI

```bash
# Run in-sample with default params (single TF)
python run_backtest.py --system <name> --config "<label>" --mode IS

# Run in-sample on 4h ETH data with custom params
python run_backtest.py --system <name> --config "<label>" --tf 4h --symbol ETH --mode IS --params '{"atr_mult": 1.5}'

# Run multi-TF (signal on daily, execute on hourly)
python run_backtest.py --system <name> --config "<label>" --signal_tf 1d --entry_tf 1h --mode IS

# Run OOS (requires prior IS run for exact system+config pair)
python run_backtest.py --system <name> --config "<label>" --mode OOS
```

---

## 15. DATA NOTES

- Data is fetched once from Binance and cached in `data/<SYMBOL>/<TF>.csv`
- If a CSV already exists, it is loaded directly — no re-fetch
- History starts from 2016-01-01 (Binance inception)
- Columns: `timestamp` (UTC), `open`, `high`, `low`, `close`, `volume`
- No forward-fill, no interpolation — raw OHLCV only

---

## 16. OLD RESEARCH ARCHIVE (old_tools/)

Three generations of pre-Hadrian research are archived in `old_tools/`:

### sysfind1 — Mean Reversion (Range Normalization)
- **Concept:** Trade reversals from range extremes
- **Best result:** ETH 1h, net EV=2.42R, n=184, WR=7.6%
- **Status:** EXTRACTED to `systems/mean_reversion_range.py`
- **Dead ends:** 5m/15m (fee-terminal), trail-to-BE, RSI/ADX filters

### sysfind2 — Opening Drive Breakout
- **Concept:** Session-based opening range breakouts
- **Best result:** BTC 15m daily, net EV=1.24R, n=1451, WR=20.9%
- **Status:** Not yet extracted (high drawdown, marginal edge)
- **Dead ends:** Most v1.0-v1.3 configs, EMA retest, exit sweep

### sysfind3 — Post-Breakout Continuation
- **Concept:** Consolidation → breakout → pause → continuation
- **Best result:** BTC H1 H1_00086, net EV=1.99R, n=190, WR=13.2%
- **Status:** EXTRACTED to `systems/post_breakout_continuation.py`
- **Dead ends:** Systems A-E (v3), EMA100 pullback, M5 FVG, daily ETH (n=30)

### TREND-DH1-001 Benchmark Audit
- The quoted benchmark (n≈104, EV≈5.06R) **does not exist** in any old_tools artifact.
- It was an aspirational target from `old_prompts/prompt.txt` and `prompt3.txt`.
- `FIX_LOG.md` and `ANALYSIS.md` document the full investigation.
- `systems/trend_dh1_001.py` is retained with a warning but produces ~0R EV.

---

*This document is maintained as part of the Hadrian Engine repository. If you find it out of date, update it before proceeding.*
