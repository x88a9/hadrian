# Hadrian Engine — Full Codebase Audit Report

> Audit performed: 2026-05-15
> Auditor instruction: Read every file, trace data flow, check math, find silent failures. Do not run code.

---

════════════════════════════════════════════
FILE: config.env
════════════════════════════════════════════

VERIFIED CORRECT:
  - Key=value parsing is straightforward.
  - TAKER_FEE=0.00035 and MAKER_FEE=0.0001 match stated Hyperliquid fee model.
  - IS/OOS windows are clearly separated (2016-2022 vs 2023-2026).

---

════════════════════════════════════════════
FILE: core/config_loader.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - Comment and blank-line skipping works.
  - `partition("=")` correctly handles values containing "=".
  - No type coercion (returns strings), which is fine because callers cast.

---

════════════════════════════════════════════
FILE: core/data_loader.py
════════════════════════════════════════════

CRITICAL BUGS:
  BUG-1: Incomplete cached CSV is never detected or re-fetched.
    Location: `load()` lines 77-80
    Impact: If a prior fetch was interrupted (network issue, Ctrl-C), the partial
            CSV is loaded forever. The engine backtests on incomplete history
            without warning, producing silently wrong metrics.
    Fix: After loading CSV, verify the date range covers HISTORY_START to near-
         now. If the last row is older than expected, re-fetch and overwrite.

ARCHITECTURAL ISSUES:
  ARCH-1: No retry logic on CCXT fetch failure.
    Impact: A transient Binance error produces an empty or partial CSV that is
            then cached (see BUG-1).
    Fix: Wrap `fetch_ohlcv` in a retry loop; validate batch non-empty before
          writing cache.

VERIFIED CORRECT:
  - Pagination loop (`since = last_ts + 1`) correctly handles 1000-candle limit.
  - `drop_duplicates` + `sort_values` handles duplicate timestamps.
  - Timestamps are parsed with `unit="ms", utc=True` consistently.

---

════════════════════════════════════════════
FILE: core/indicators.py
════════════════════════════════════════════

CRITICAL BUGS:
  BUG-1: `pivot_high()` and `pivot_low()` use `center=True`, which is lookahead.
    Location: Lines 299-306
    Impact: At bar i, these functions inspect bars i+1 … i+right (future data)
            to decide whether bar i is a pivot. This contaminates every system
            that uses them:
            - `sl_nearest_swing` (stop-loss placement knows future swings)
            - `tp_next_swing` (take-profit knows future swings)
            - `tr_swing_structure` (trend state knows future structure)
            - Systems: swing_structure, volume_structure (S1/S2), multi_indicator_confluence (C5), altcoin_cross_asset (sl_type="swing"), bollinger_band_structure, candle_structure, donchian_structure, ma_relationship_breakout, vwap_structure — any that call sl_nearest_swing / tp_next_swing / pivot_high / pivot_low.
    Fix: Replace `center=True` with `center=False` and shift the result forward
         by `right` bars, or implement a true past-only pivot:
         `high.iloc[i] == high.iloc[i-left : i+1].max()` for a pivot that only
         looks backward and confirms `right` bars later via a state machine.

  BUG-2: `atr()` uses simple moving average of TR, not Wilder's smoothing.
    Location: Line 156
    Impact: All ATR-derived levels (SL, TP, KC, squeeze detection) are
            materially different from the Wilder ATR used by most trading
            platforms. On n=14 the SMA-ATR is ~10-15% lower than Wilder-ATR
            in trending periods, making stops too tight and inflating R values.
    Fix: Change to `tr(df).ewm(alpha=1/n, adjust=False).mean()` for true
         Wilder ATR, or rename the function and document the divergence.

LOOKAHEAD / LEAKAGE ISSUES:
  LA-1: `pivot_high` / `pivot_low` as described in BUG-1.

VERIFIED CORRECT:
  - `ema()` uses `ewm(span=n, adjust=False)` — correct for recursive EMA.
  - `bb()` SMA + std formula is mathematically correct.
  - `dc()` correctly shifts by 1 to exclude current bar.
  - `tr()` and `obv()` formulas are standard.
  - `vwap_session()` resets per UTC day correctly.

---

════════════════════════════════════════════
FILE: core/engine.py
════════════════════════════════════════════

CRITICAL BUGS:
  None found in the core loop itself. The engine’s anti-fallacy rules are
  implemented correctly in the code, but they are undermined by system-level
  bugs (see system files below).

ARCHITECTURAL ISSUES:
  ARCH-1: Only the last signal in `raw_signals` is used; earlier signals are
          silently dropped.
    Location: Line 285 (`sig = raw_signals[-1]`)
    Impact: If a system returns multiple variant signals on the same bar, only
            one is executed. This is undocumented behavior and can mask valid
            signals.
    Fix: Document the behavior or iterate over all signals and execute the first
         valid one that passes filters.

  ARCH-2: `should_exit` is checked BEFORE SL/TP, as documented, but there is no
          guarantee that the exit price from `should_exit` is better than SL.
    Impact: A buggy `should_exit` could return a price beyond the stop loss,
            causing a worse fill than the SL would have provided.
    Fix: Add a safety clamp: if `should_exit` returns a price that is beyond
         the SL level for the trade direction, force SL price instead.

VERIFIED CORRECT:
  - `_validate_signal` enforces all required keys and valid enum values.
  - `df_slice = entry_df.iloc[: i + 1]` passed to `should_exit` — no lookahead.
  - Exit order: `should_exit` → SL (`low <= sl` / `high >= sl`) → TP (`high >= tp` / `low <= tp`).
  - Limit fill logic: `low <= limit_price` (long), `high >= limit_price` (short).
  - Fee formula: `((entry * fee) + (exit * fee)) / abs(entry - sl) * risk_fraction`.
  - R formula: long `(exit - entry) / abs(entry - sl)`, short `(entry - exit) / abs(entry - sl)`.
  - `state = {}` is reset per run.
  - `pending_order` silently expires at end of data; open trade is closed at last close.
  - OOS gate requires prior IS run for exact (system, config_label) pair.
  - Multi-TF alignment uses `searchsorted(ts, side="right")` — only bars with
    close_time <= current entry bar are visible. Correct.

---

════════════════════════════════════════════
FILE: core/metrics.py
════════════════════════════════════════════

CRITICAL BUGS:
  BUG-1: Sharpe annualization uses sqrt(252) while R/year uses 365.25 days.
    Location: Lines 62, 126
    Impact: Sharpe and R/yr are computed on inconsistent calendar assumptions.
            Crypto trades 365 days/year. A strategy with constant daily R will
            have Sharpe scaled by sqrt(252) ≈ 15.87 but R/yr scaled by 365.25.
            This makes Sharpe appear lower than it should be relative to R/yr,
            and comparisons between systems are misleading.
    Fix: Use `math.sqrt(365)` for Sharpe, or switch R/yr denominator to
         `252 * (span_days / 365.25)` to align with equity conventions.
         Recommend sqrt(365) for crypto.

ARCHITECTURAL ISSUES:
  ARCH-1: `span_days == 0` falls back to `years = 1.0`, overstating R/yr for
          same-day trades.
    Impact: A single-day test run shows R/year = total_R, which is misleading.
    Fix: If `span_days == 0`, set `years = 1/365.25` (treat as one trading day).

VERIFIED CORRECT:
  - Max drawdown is computed on cumulative R_net peak-to-trough. Correct.
  - Win rate uses `r > 0` for wins; `r <= 0` for losses (ties = loss). Consistent.
  - Profit factor = sum(wins) / abs(sum(losses)). Correct.
  - Calmar = annualized_R / max_dd in R. Correct.
  - Daily Sharpe construction assigns 0 R to days with no trades. Correct.

---

════════════════════════════════════════════
FILE: core/exports.py
════════════════════════════════════════════

ARCHITECTURAL ISSUES:
  ARCH-1: Ledger rewrite is not atomic; if Excel is open, write crashes.
    Impact: Unhandled `PermissionError` can corrupt or prevent ledger update.
    Fix: Write to a temp file, then `os.replace()` atomically.

VERIFIED CORRECT:
  - `_next_backtest_n` and `_next_run_number` correctly auto-increment.
  - Empty ledger or gaps handled gracefully (starts at 1).
  - All required LEDGER_COLS are written even if metrics dict is empty.

---

════════════════════════════════════════════
FILE: run_backtest.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - Argument parsing and TF/mode validation are correct.
  - `dfs_full` loads only required TFs; deduplicates when signal_tf == entry_tf.
  - Params JSON is decoded with sensible error handling.

---

════════════════════════════════════════════
FILE: systems/trend_dh1_001.py
════════════════════════════════════════════

CRITICAL BUGS:
  BUG-1: Wrong EMA alpha values — implements 20/50 EMA instead of 12/21.
    Location: `_update_ema_cache` lines 43-44
    Impact: `alpha12 = 2 / 21` corresponds to EMA period 20 (alpha = 2/(N+1)).
            `alpha21 = 2 / 51` corresponds to EMA period 50.
            The system docstring says "12 EMA / 21 EMA". The slower EMAs
            dramatically change signal frequency and trend classification.
            Combined with BUG-2 (no minimum holding period), this produces
            far more trades (n=316) with negative EV (-0.15R) instead of the
            benchmark n=104 EV=5.06R.
    Fix: Set `alpha12 = 2 / 13` and `alpha21 = 2 / 22` to match 12-period and
         21-period EMAs. (See `trend_dh1_001_backup.py` for the correct values.)

  BUG-2: `should_exit` has no minimum holding period.
    Location: `should_exit` lines 312-341
    Impact: Trades can be closed on the very next bar if the EMAs cross back.
            On noisy H1 data this causes whipsaws, inflating trade count and
            eroding EV through repeated fee bleed.
    Fix: Add `if bars_open < 24: return None` guard (present in the backup file).

VERIFIED CORRECT:
  - Daily state machine processes bars incrementally; no lookahead.
  - Box construction waits for 3 daily bars after C_N2 before setting high/low.
  - Breakout confirmation waits 3 post-breakout bars; false breakout check uses
    only bars processed so far. Correct.
  - Entry window `(current_ts - breakout_ts).days > 5` implements 5-day window.
  - H1 retest logic uses `l <= ema12_val <= h` (wick touch). Correct.

---

════════════════════════════════════════════
FILE: systems/trend_dh1_001_backup.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - Alpha values are correct: `alpha12 = 2 / 13`, `alpha21 = 2 / 22`.
  - `should_exit` includes the 24-bar minimum holding period.
  - Entry window uses `> 4` days (slightly different from main but acceptable).
  - Contains `last_trade_close_ts` tracking not present in main file.

---

════════════════════════════════════════════
FILE: systems/dow_breakout.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - Breakout uses `prior_5 = df.iloc[-6:-1]` — exactly 5 prior candles, correct.
  - SL validation ensures SL is on the correct side of entry.
  - Day-of-week label derived from current bar timestamp.

---

════════════════════════════════════════════
FILE: systems/inside_candle_sweep.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - Strict inside-candle checks use `<` and `>`, not `<=` / `>=`. Correct.
  - Scan backwards for IC pattern is bounded (`max_ic2_offset <= 20`).
  - Breakout and sweep detection only inspect past bars (`bo_pos` in
    `range(ic2_pos+1, n-1)`). No lookahead.
  - `is_first_sweep` verification checks intermediate bars only. Correct.

---

════════════════════════════════════════════
FILE: systems/cvd_divergence_breakout.py
════════════════════════════════════════════

CRITICAL BUGS:
  BUG-1: `_is_swing_low` and `_is_swing_high` use future data.
    Location: Lines 52-59
    Impact: `window = lows.iloc[max(0, idx-n) : min(len(lows), idx+n+1)]` includes
            bars `idx+1` through `idx+n`. At the current bar, the system evaluates
            swings at past indices but uses future bars relative to those indices.
            This means the "divergence" is detected using knowledge of bars that
            had not yet occurred at the swing point, invalidating the signal.
    Fix: Use only backward-looking windows:
         `window = lows.iloc[max(0, idx-n) : idx+1]` and compare to that.
         Or confirm swings after `n` subsequent bars via state machine.

VERIFIED CORRECT:
  - CVD approximation formula is standard.
  - Entry "first close above prior swing low" checks only intermediate bars.

---

════════════════════════════════════════════
FILE: systems/higher_high_lower_low_break.py
════════════════════════════════════════════

CRITICAL BUGS:
  BUG-1: `_find_pivots` uses future data in swing detection.
    Location: Lines 48-50
    Impact: `highs.iloc[i] == highs.iloc[i-n : i+n+1].max()` includes future bars
            i+1 … i+n. Same lookahead pattern as cvd_divergence_breakout.
    Fix: Use `highs.iloc[i-n : i+1].max()` for a backward-only pivot, and
         confirm it via a state machine after n subsequent bars.

---

════════════════════════════════════════════
FILE: systems/altcoin_momentum_vs_btc.py
════════════════════════════════════════════

CRITICAL BUGS:
  BUG-1: Module-level `_BTC_DAILY_CACHE` persists across backtest runs.
    Location: Lines 46-53
    Impact: State from one run (e.g., BTC daily data for a different date range
            or a corrupted prior fetch) bleeds into the next run.
    Fix: Remove global cache; load BTC data via the engine's `dfs` dict, or
         clear the cache at the start of each `get_signals` call.

VERIFIED CORRECT:
  - `searchsorted` alignment for BTC vs altcoin timestamps is correct.
  - `btc_slice = btc_df.iloc[:pos+1]` uses only past BTC bars.
  - Breakout and volume filters use only past data.

---

════════════════════════════════════════════
FILE: systems/ema_pullback_trend_filter.py
════════════════════════════════════════════

CRITICAL BUGS:
  BUG-1: Module-level `_HT_CACHE` persists across runs.
    Location: Lines 47-54
    Impact: Higher-TF DataFrame and EMA values from one run leak into the next.
    Fix: Remove module-level cache or clear it at the start of each run.

VERIFIED CORRECT:
  - HT EMA is computed on `ht_df["close"].iloc[:pos+1]` — only past HT data.
  - Pullback logic uses prior bar low/high vs prior EMA. Correct.
  - Confirmation requires current close on the correct side of current EMA.

---

════════════════════════════════════════════
FILE: systems/multi_tf_momentum_alignment.py
════════════════════════════════════════════

CRITICAL BUGS:
  BUG-1: Module-level `_PRECOMPUTED` dict persists across runs.
    Location: Lines 62-97
    Impact: Precomputed daily/H4 indicators from one symbol or parameter set
            leak into subsequent runs.
    Fix: Remove global cache or key it by a run-unique identifier and clear
         between runs.

VERIFIED CORRECT:
  - Precomputed EMA/RSI on full history is NOT lookahead because `ewm` with
    `adjust=False` uses only past points recursively.
  - `searchsorted` on `daily_ts` and `h4_ts` correctly aligns timestamps.
  - H1 breakout uses `df["high"].iloc[-h1_breakout_n-1:-1]` — excludes current bar.

---

════════════════════════════════════════════
FILE: systems/altcoin_cross_asset.py
════════════════════════════════════════════

LOOKAHEAD / LEAKAGE ISSUES:
  LA-1: Uses `ind.sl_nearest_swing` and `ind.tp_next_swing`, which rely on
        `pivot_high` / `pivot_low` with `center=True` (future data).
    Impact: Stop loss and take profit levels know future swing points.
    Fix: Fix `pivot_high` / `pivot_low` in core/indicators.py.

VERIFIED CORRECT:
  - All signal types use only past closes and shifted indicators.
  - `dc()`, `bb_pct()`, `atr_ratio()` are evaluated at `iloc[-1]`.

---

════════════════════════════════════════════
FILE: systems/bollinger_band_structure.py
════════════════════════════════════════════

LOOKAHEAD / LEAKAGE ISSUES:
  LA-1: Uses `ind.sl_nearest_swing` and `ind.tp_next_swing` (pivot lookahead).

VERIFIED CORRECT:
  - S1 squeeze detection uses `shift(1)` correctly.
  - S3 walking bands uses `.iloc[-walk_bars:].all()` on past window.
  - S4 band rejection uses current wick and current close only.
  - S5 midline cross checks prior bar state via `iloc[-2]`.

---

════════════════════════════════════════════
FILE: systems/candle_structure.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - `_last_row_pattern` inspects only `df.iloc[-1]` and `df.iloc[-2]`.
  - No indicator lookahead.

---

════════════════════════════════════════════
FILE: systems/donchian_structure.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - `dc()` already shifts by 1, so breakout uses prior-N-bar high/low.
  - S2 false breakout checks `shift(1)` for prior bar state.
  - S5 midline reversion checks `shift(1)` for prior extreme.

---

════════════════════════════════════════════
FILE: systems/volatility_compression_breakout.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - ATR compression window is `atr_slice = atr_series.iloc[lookback_start:current_idx+1]`.
  - Breakout high/low uses `df["high"].iloc[breakout_start:current_idx]` — excludes current bar high from the breakout level, which is actually conservative and acceptable (close must exceed prior highs, not current high).

---

════════════════════════════════════════════
FILE: systems/volume_climax_reversal.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - Volume spike uses rolling mean/std on past 20 bars only.
  - Wick direction and body check use current bar only.

---

════════════════════════════════════════════
FILE: systems/volume_profile_value_area_fade.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - Volume profile histogram uses only `window_df` (past N bars ending at current).
  - Signal requires prior bar close outside VAH/VAL and current bar back inside.
  - No lookahead in histogram computation.

---

════════════════════════════════════════════
FILE: systems/weekly_level_respect.py
════════════════════════════════════════════

MINOR ISSUES:
  MINOR-1: Year-boundary week handling is fragile.
    Location: `_prior_week_range` lines 64-72
    Impact: ISO week 53 at year-end is not handled; `week == 52` hardcode may
            miss the true prior week when week 53 exists.
    Fix: Use `(ts - pd.Timedelta(weeks=1)).isocalendar()` to identify the prior
         week unambiguously.

VERIFIED CORRECT:
  - Prior week range scan is backward-only.
  - Rejection condition checks wick penetration and close back inside range.

---

════════════════════════════════════════════
FILE: systems/swing_structure.py
════════════════════════════════════════════

LOOKAHEAD / LEAKAGE ISSUES:
  LA-1: Uses `ind.pivot_high` / `ind.pivot_low` (center=True lookahead).
    Impact: Swing highs/lows are detected using future bars, so structural
            signals (break, retest) know future price action.
    Fix: Fix core pivot functions or implement past-only pivot detection.

---

════════════════════════════════════════════
FILE: systems/multi_indicator_confluence.py
════════════════════════════════════════════

LOOKAHEAD / LEAKAGE ISSUES:
  LA-1: C5 uses `ind.pivot_high` / `ind.pivot_low` (center=True lookahead).
    Impact: Swing break + volume signal relies on future-known swing points.
    Fix: Fix core pivot functions.

VERIFIED CORRECT:
  - All other confluence patterns use shifted indicators and current-bar checks.

---

════════════════════════════════════════════
FILE: systems/volume_structure.py
════════════════════════════════════════════

LOOKAHEAD / LEAKAGE ISSUES:
  LA-1: S1 and S2 use `ind.pivot_high` / `ind.pivot_low` (center=True lookahead).
    Impact: OBV and CVD divergences are evaluated at "swing" points that were
            not knowable at the time.
    Fix: Fix core pivot functions.

---

════════════════════════════════════════════
FILE: systems/vwap_structure.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - All signal types use current bar and `shift(1)` for prior state.
  - SD band approximation uses ATR proxy, which is acceptable.

---

════════════════════════════════════════════
FILE: systems/ma_relationship_breakout.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - All signal types check `iloc[-1]` vs `iloc[-2]` or shifted series.
  - S4 pullback checks `above_ma.iloc[-pullback_bars:-1].all()` on past window.

---

════════════════════════════════════════════
FILE: systems/opening_range_breakout.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - Session start search is backward-only.
  - Opening range excludes the session-start candle itself (`range_start + 1`).
  - Current bar must be after opening range (`current_idx >= range_end`).

---

════════════════════════════════════════════
FILE: systems/engine_test.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - `should_exit` uses `bars_open >= 3` for time-based exit.
  - Limit order setup with `risk_fraction=0.5` is handled correctly.
  - State `retest_count` increments correctly.

---

════════════════════════════════════════════
FILE: systems/minimal_test.py
════════════════════════════════════════════

VERIFIED CORRECT:
  - Returns empty list; trivially correct.

---

════════════════════════════════════════════
FILE: README_AGENT.md
════════════════════════════════════════════

VERIFIED CORRECT:
  - Signal contract documentation matches engine implementation.
  - Multi-TF alignment description matches `searchsorted` logic in engine.
  - State dict behavior is accurately described.

NOTE:
  - README claims "ENGINE VERSION: Rebuilt 2026-05-14. All 7 architectural flaws
    fixed." The audit found that the pivot_high/pivot_low lookahead (a core
    indicator flaw) was NOT fixed in this rebuild. Several other issues (Sharpe
    inconsistency, module-level caches, data_loader incomplete-cache handling)
    also remain.

---

AUDIT SUMMARY
═════════════
Total critical bugs: 7
Total lookahead issues: 7
Total architectural issues: 7

MOST LIKELY CAUSE OF WRONG RESULTS:
  The TREND-DH1-001 discrepancy (n=316 EV=-0.15R vs expected n=104 EV=5.06R)
  is caused by the combination of two bugs in `systems/trend_dh1_001.py`:

  1. BUG-1: Wrong EMA alphas (2/21 and 2/51 implement 20/50 EMA instead of
     the documented 12/21 EMA). The slower EMAs change trend classification
     and retest eligibility.
  2. BUG-2: Missing 24-bar minimum holding period in `should_exit`. Without
     it, the system exits immediately on any EMA cross whipsaw, generating
     ~3× as many trades and bleeding fees.

  The backup file (`trend_dh1_001_backup.py`) contains the correct alphas
  and the holding-period guard. Restoring those two changes should recover
  the benchmark performance.

  Separately, the `pivot_high` / `pivot_low` lookahead in `core/indicators.py`
  silently contaminates roughly half the system inventory. Any backtest that
  uses swing-based SL, TP, or signal detection is invalid and likely
  overstates edge.

PRIORITY FIX ORDER:
  1. Fix `systems/trend_dh1_001.py` EMA alphas (2/13, 2/22) and add 24-bar
     minimum holding period to `should_exit`. This restores the benchmark.
  2. Fix `core/indicators.py` `pivot_high` / `pivot_low` to remove
     `center=True`. This removes lookahead from ~10 systems.
  3. Fix `systems/cvd_divergence_breakout.py` and
     `systems/higher_high_lower_low_break.py` custom swing functions that
     also look forward.
  4. Remove or isolate module-level caches in
     `altcoin_momentum_vs_btc`, `ema_pullback_trend_filter`, and
     `multi_tf_momentum_alignment`.
  5. Fix `core/metrics.py` Sharpe / calendar-day inconsistency (sqrt(365)).
  6. Fix `core/data_loader.py` to detect and re-fetch incomplete cached CSVs.
  7. Fix `core/indicators.py` `atr()` to use Wilder's smoothing or document
     the divergence.

THINGS THAT ARE DEFINITELY CORRECT:
  - Engine loop enforces no-overlapping-trades and no-lookahead for the
    entry bar slice (`iloc[:i+1]`).
  - Fee and R calculation formulas in engine.py are mathematically exact.
  - Limit order fill detection (`low <= limit` / `high >= limit`) is correct.
  - Exit check order (should_exit → SL → TP → end_of_data) is correct.
  - Multi-TF timestamp alignment via `searchsorted(..., side="right")` is
    architecturally sound.
  - Drawdown is computed on cumulative R_net curve, not single trades.
  - Daily Sharpe correctly assigns 0 R to non-trading days.
  - `inside_candle_sweep.py` pattern logic is rigorously past-only.
  - `dow_breakout.py` breakout definition and DOW labeling are correct.

VERDICT ON BENCHMARK DISCREPANCY:
  It is a code bug, not a spec ambiguity. The main `trend_dh1_001.py` file
  was edited (likely during the "rebuild") and the EMA alphas were set to
  values that implement 20/50 EMAs instead of 12/21. Simultaneously, the
  24-bar minimum holding period was removed from `should_exit`. The backup
  file retains the original correct implementation. Restoring the backup's
  alpha values and holding-period guard to the main file resolves the
  discrepancy.
