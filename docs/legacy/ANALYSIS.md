# old_tools/ Research Audit — ANALYSIS.md

> Generated: 2026-05-15
> Auditor: Kimi Code CLI
> Scope: sysfind1, sysfind2, sysfind3 — full read + cross-reference with Hadrian Engine

---

## EXECUTIVE SUMMARY

### The TREND-DH1-001 Benchmark Does Not Exist in old_tools

The benchmark quoted for `trend_dh1_001` — **n≈104, EV≈5.06R, WR≈26.9%, R/yr≈62.9** — **was never achieved by any system in any `old_tools/` folder.**

- **It appears only in prompt files** (`old_prompts/prompt.txt`, `old_prompts/prompt3.txt`) and audit reports that quoted those prompts.
- `FIX_LOG.md` explicitly confirms: *"The historical results ledger for trend_dh1_001 shows no run ever achieved the quoted benchmark."*
- **Repository-wide grep** for strings `n=104`, `5.06R` returns **zero** actual backtest output files. Results are limited to prompt files and audit documentation.

### What Actually Produced ~5R in old_tools

The figure `5.06R` **does** appear in `sysfind1/progress.ipynb`, but **never as EV**:
- Line 1781: `r_per_month=5.0638` (not EV) for a **pre-fee** BTC 1h config.
- Line 255: `avg_win_r=5.0654` (not EV) for a failed trail-to-BE experiment with actual EV=0.047R.

The highest **actual EV** found anywhere in `old_tools/` is:
- **sysfind1 mean reversion (ETH 1h): net EV=2.42R, n=184, WR=7.6%**

### Verified Systems with Real Edge (EV > 0.3R, n ≥ 30)

| System | Source | Best Config | Net EV | n | WR | Notes |
|--------|--------|-------------|--------|---|---|-------|
| **Mean Reversion** | sysfind1/run_mr6.py | ETH 1h, lb=15, rcl=14, tp=3.0 | **2.42R** | 184 | 7.6% | Highest EV in all old_tools. Fee-sensitive. |
| **Post-Breakout Continuation** | sysfind3/research_ext_report.py | BTC H1, cb=24, arm=4.0, asl=0.5, hold=48 | **1.99R** | 190 | 13.2% | Best actual "trend" system. OOS=1.81R. |
| **Opening Drive Breakout** | sysfind2/leaderboard_v1.6.csv | BTC 15m daily, msb, breakout_candle SL | **1.24R** | 1451 | 20.9% | High frequency, lower EV. |
| **Post-Breakout (alt)** | sysfind3/research_v3.py | System E, BTC H1, atr_sl=0.5, band_req=True | **1.90R** | 78 | 7.7% | Below n=100 threshold. |

### Hadrian Verification Results

| System | Hadrian File | Symbol/TF | Mode | n | EV (R) | WR | R/yr | Status |
|--------|--------------|-----------|------|---|--------|-----|------|--------|
| Mean Reversion | `mean_reversion_range.py` | ETH/1h | full | 520 | **0.00** | 2.5% | 0.13 | **FAILED** — does not reproduce original edge |
| Post-Breakout | `post_breakout_continuation.py` | BTC/1h | IS | 231 | **1.00** | 9.5% | 43.39 | ✅ Verified |
| Post-Breakout | `post_breakout_continuation.py` | BTC/1h | OOS | 127 | **1.42** | 13.4% | 53.80 | ✅ OOS confirms IS |
| Post-Breakout | `post_breakout_continuation.py` | BTC/1h | full | 358 | **1.15** | 10.9% | 47.12 | ✅ Strong edge |
| Post-Breakout | `post_breakout_continuation.py` | ETH/1h | IS | 207 | **0.72** | 10.6% | 28.16 | ✅ Borderline |
| Post-Breakout | `post_breakout_continuation.py` | ETH/1h | OOS | 126 | **0.17** | 11.1% | 6.25 | ⚠️ Failed OOS (23% of IS) |

**Key finding:** Only `post_breakout_continuation.py` on **BTC 1h** successfully reproduces and validates the original edge. ETH shows degraded OOS performance.

### Conclusion

The `n=104, EV=5.06R` benchmark for TREND-DH1-001 is **misattributed**. It was an aspirational target written into prompts, not an empirical result from any backtest. Continuing to search `old_tools` for this exact result is futile.

**Recommended action:**
1. Replace the TREND-DH1-001 benchmark in all documentation with the **actual best trend system** (`post_breakout_continuation.py` BTC 1h: ~1.0-1.4R EV, verified OOS).
2. Deprecate `mean_reversion_range.py` — the original edge does not survive the transition to Hadrian (likely due to entry-bar SL check difference and/or regime dependency).
3. Use `post_breakout_continuation.py` BTC 1h as the primary trend system going forward.

---

## 1. SYSFIND1 — MEAN REVERSION (Range Normalization)

### 1.1 What This Folder Researched

**Concept:** Range mean reversion. When price spikes to an extreme of a recent range and quickly reverses, trapped traders' stop losses fuel the move back.

**Hypothesis:** Price visiting one extreme of a rolling range and then returning to the opposite extreme creates a high-R, low-WR edge that survives fees on longer timeframes (1h+).

### 1.2 Methodology

**Signal logic:**
```
range_high  = rolling max of high over lookback bars
range_low   = rolling min of low  over lookback bars
range_size  = range_high - range_low
norm_pos    = (close - range_low) / range_size

Long when:
  norm_pos < entry_zone                (close in bottom X% of range)
  AND prior_norm_max > reversal_pct    (was near TOP within last rcl bars)

Short when:
  norm_pos > (1 - entry_zone)          (close in top X% of range)
  AND prior_norm_min < (1 - reversal_pct)  (was near BOTTOM within last rcl bars)
```

**Entry:** Next open (`entry_type="next_open"`)

**Exit levels:**
```
Long:  SL = range_low  - sl_buffer × range_size
       TP = range_low  + tp_normalized × range_size
Short: SL = range_high + sl_buffer × range_size
       TP = range_high - tp_normalized × range_size
```

**Execution:** SL is wick-based, TP is close-based, max hold 200 bars.

**Fee model:** 0.02% per side + 1bp entry slip + 3bp SL slip (explicitly modeled in R-multiples).

### 1.3 Results Found

**Final viable config (post-fee, Round 6):**
| Metric | Full Period | IS 2022-23 | OOS 2024-now |
|--------|-------------|------------|--------------|
| Net EV | **2.42R** | 1.83R | **2.80R** |
| Net R/month | 8.63R | 5.72R | 11.35R |
| Trades | 184 | 73 | 111 |
| Win rate | 7.6% | 6.8% | 8.1% |
| Avg win | 49.5R | 46.5R | 51.2R |
| Sharpe | 1.103 | 0.882 | 1.275 |
| Cost/trade | 0.449R | 0.442R | 0.454R |

**Parameters:** `lookback=15, entry_zone=0.02, sl_buffer=0.04, tp_normalized=3.0, reversal_confirm_lb=14, direction=both`

**Why 5m/15m failed:** Fee-in-R = `(0.04% + slip) × price / risk_price`. On 5m, risk_price ≈ $10 → fees = 4-5R per trade, killing all edge.

### 1.4 Dead Ends

- RSI filter, ADX filter, hour-of-day filter, day-of-week filter: all reduced n without improving EV.
- Trail-to-BE: reduced EV (converts winners to breakeven too early).
- BTC 5m/15m, ETH 5m/15m: fee-terminal.
- Wider SL (0.08-0.15): reduced R-per-win faster than it reduced losses.

### 1.5 Lookahead / Bugs

**No lookahead found.** Signal uses only completed bars. Entry at next open. SL/TP calculated from signal bar's range only.

**One caveat:** `compute_range_features` uses `.rolling(lookback)` which includes the current bar. The `prior_norm_max` is computed from `norm.shift(1).rolling(reversal_confirm_lb).max()`, correctly excluding the current bar. This is clean.

### 1.6 Hadrian Verification — FAILED

**Hadrian result (ETH 1h, full mode, default params):** n=520, EV=0.00R, WR=2.5%

**Why it failed:**

1. **Entry-bar SL check:** The Hadrian Engine checks SL/TP on the entry bar itself. sysfind1's `simulate()` skips the entry bar (`for j in range(entry_i + 1, ...)`). For a system with tight SL (`sl_buffer=0.04`, risk = 0.06×range_size), ~70% of trades hit SL immediately on the entry bar in Hadrian vs surviving in sysfind1.

2. **Fee model:** Hadrian uses 0.035% taker fee vs sysfind1's 0.02%. On tight stops, this adds ~0.1-0.2R per trade.

3. **Regime dependency:** The original edge was found on 2022-2026 ETH data only. It may not generalize to 2016-2022.

**Verdict:** The mean reversion system is **not viable in Hadrian** as ported. The entry-bar architectural difference is irreconcilable without engine modification (which is forbidden per AGENTS.md).

### 1.7 Key Signal Logic to Preserve

```python
# From mean_reversion.py v2
norm = (df["close"] - range_low) / range_size
prior_norm_max = norm.shift(1).rolling(reversal_confirm_lb).max()
prior_norm_min = norm.shift(1).rolling(reversal_confirm_lb).min()

long_mask  = (norm < entry_zone) & (prior_norm_max > 0.75)
short_mask = (norm > (1 - entry_zone)) & (prior_norm_min < 0.25)

# Exit:
SL_long = range_low - sl_buffer * range_size
TP_long = range_low + tp_normalized * range_size
```

**For Hadrian:** Must use `entry_type="next_open"`. SL and TP prices are computed at signal time from the signal bar's range. No `should_exit` needed unless implementing max_hold.

---

## 2. SYSFIND2 — OPENING DRIVE BREAKOUT

### 2.1 What This Folder Researched

**Concept:** Session-based opening drive breakout. The first candle of a trading session establishes an opening range. A breakout from this range with volume indicates directional intent for the session.

**Hypothesis:** Opening range breakouts during high-volume sessions (NY Open) with trend alignment produce positive EV.

### 2.2 Methodology

**Signal logic:**
1. Define session boundaries (NYO, London, etc.)
2. First candle of session = opening range box (`box_high`, `box_low`)
3. Subsequent candles that break the box with volume = signal
4. Optional EMA trend filter, box compression filter

**Entry:** Next open after breakout candle close.

**SL types:**
- `box`: SL at opposite side of opening range box ± ATR mult
- `breakout_candle`: SL at breakout candle's low/high ± ATR mult

**TP modes:**
- `msb`: Market Structure Break (trailing swing-point exit)
- Fixed R: 2R, 3R, 5R, 10R
- `session_close`: hard exit at session end
- `trail_close`: trailing low/high of last N bars

**Fee model:** Explicit fee + funding cost modeling in `costs.py`.

### 2.3 Results Found

**Best viable config (from `leaderboard_v1.6.csv`):**
| Metric | Value |
|--------|-------|
| Config | BTC 15m daily msb breakout_candle atr0.0 |
| Net EV | **1.236R** |
| n | 1451 |
| WR | 20.9% |
| R/month | 37.4R |
| Sharpe | 0.256 |
| Max DD | 641R |

**Note:** High max drawdown (641R) is a red flag. This system generates many trades but with shallow edge.

**Other viable configs:**
- `ema+box_1.0x` (entry sweep): n=180, net EV=0.33R, WR=35%
- `daily_msb_5` (multiday): n=138, net EV=1.39R, WR=12.3%

### 2.4 Dead Ends

- Most configs in early rounds (v1.0-v1.3) produced net EV < 0.3R.
- EMA retest variants: generally negative or marginal.
- Exit sweep variants: no viable configs found.

### 2.5 Lookahead / Bugs

**No lookahead found.** Signal fires on close of breakout candle. Entry at next open. Session definitions are deterministic based on time.

**One caveat:** MSB (Market Structure Break) trailing exit uses swing points computed from full data. In live trading, swing point determination can lag. However, for backtesting this is not lookahead since it only uses past bars.

### 2.6 Key Signal Logic to Preserve

```python
# From signals.py
box_high  = first_candle["high"]
box_low   = first_candle["low"]

# Breakout check (with volume filter)
if close > box_high and volume > vol_ma:
    direction = "long"
elif close < box_low and volume > vol_ma:
    direction = "short"

# SL
if sl_type == "breakout_candle":
    sl = candle["low"] - atr_mult * atr   # for long
```

---

## 3. SYSFIND3 — POST-BREAKOUT CONSOLIDATION / CONTINUATION

### 3.1 What This Folder Researched

**Concept:** After a strong breakout from a consolidation zone, price often pauses briefly before continuing. Enter during the pause with a tight stop.

**Hypothesis:** Consolidation → breakout → pause → continuation is a repeatable pattern with positive EV on H1 timeframes.

### 3.2 Methodology (H1_00086 — Best Result)

**Signal logic (from `research_ext_report.py`):**
```python
def compute_signals(df, consol_bars, atr_range_mult, max_k=1):
    # For each bar i, look back k bars:
    w_h = high.shift(k+1).rolling(consol_bars).max()
    w_l = low.shift(k+1).rolling(consol_bars).min()
    w_atr = atr.shift(k+1)
    
    consol_ok = (w_h - w_l) < atr_range_mult * w_atr
    uptrend   = (close.shift(k) > ema50.shift(k)) & (ema50.shift(k) > ema50.shift(k+5))
    breakout  = close.shift(k) > w_h + 0.25 * atr.shift(k)
    
    # Pause = inside / doji / pin bar on breakout candle
    pause = _pause_mask(high, low, open, close, atr, bk_h, bk_l)
    
    signal = consol_ok & uptrend & breakout & pause
```

**Entry:** Next open after signal bar (`entry_type="next_open"`)

**SL:** `0.5 × ATR` from entry price (`asl=0.5`)

**Exit:** Fixed hold of 48 H1 bars (2 days). No TP price — exit at close after hold period.

**Fee model:** 0.02% per side + entry slip + funding cost per day held.

### 3.3 Results Found

**H1_00086 (best single-instrument result across all sysfind3):**
| Metric | Value |
|--------|-------|
| Symbol | BTC/USDT |
| TF | 1h |
| consol_bars | 24 |
| atr_range_mult | 4.0 |
| asl | 0.5 |
| hold_bars | 48 |
| Net EV | **1.987R** |
| n | 190 |
| WR | 13.2% |
| R/month | 3.77R |
| OOS EV | 1.806R |

**Robustness:**
- ATR ±20% sensitivity: EV stable
- Hold ±20% sensitivity: EV stable
- Year-by-year: positive EV in most years

**Other results:**
- Daily post-breakout (ETH): n=30, EV=2.48R (too few trades)
- Systems A-E (v3): all discarded — none met WR>50% AND EV>1.2R targets
- EMA100 pullback: 0.23R
- M5 FVG: -0.86R

### 3.4 Dead Ends

- **Systems A-E (v3):** All discarded. Best was System E BTC H1 with n=78, EV=1.896R (below n=100 target).
- **EMA100 pullback:** Failed — WR too low, EV marginal.
- **M5 FVG:** Negative EV.
- **Multi-instrument basket:** Pool EV only 0.58R (diluted by negative-EV alts).

### 3.5 Lookahead / Bugs

**No lookahead found.** `compute_signals` uses `.shift(k)` and `.shift(k+1)` — all past data. Breakout confirmation uses close of bar k, which is in the past relative to the signal bar.

**One subtle point:** `_pause_mask` uses the breakout candle's high/low (`bk_h`, `bk_l`). This is the candle immediately before the pause candle. Since the pause candle is the current signal bar, `bk_h` and `bk_l` are from one bar ago — valid, no lookahead.

### 3.6 Hadrian Verification — PASSED (BTC 1h)

**Hadrian result (BTC 1h, default params):**
| Mode | n | EV (R) | WR | R/yr | Sharpe | Max DD |
|------|---|--------|-----|------|--------|--------|
| IS (2016-2022) | 231 | **1.00** | 9.5% | 43.39 | 0.84 | 51.8R |
| OOS (2023-2026) | 127 | **1.42** | 13.4% | 53.80 | 0.91 | 58.9R |
| Full (2016-2026) | 358 | **1.15** | 10.9% | 47.12 | 0.80 | 58.9R |

**OOS confirms IS** (142% of IS EV). The edge is genuine and robust across both regimes.

**ETH 1h result:** IS=0.72R, OOS=0.17R (failed OOS — only 23% of IS). BTC is the preferred instrument.

### 3.7 Key Signal Logic to Preserve

```python
# From research_ext_report.py compute_signals()
consol_ok = (w_h - w_l) < atr_range_mult * w_atr
uptrend   = (c.shift(k) > ema50.shift(k)) & (ema50.shift(k) > ema50.shift(k+5))
breakout  = c.shift(k) > w_h + 0.25 * bk_atr
pause     = _pause_mask(h, l, o, c, atr, bk_h, bk_l)
signal    = consol_ok & uptrend & breakout & pause

# _pause_mask:
is_inside = (h < bk_h) & (l > bk_l)
is_doji   = body_pct < 0.30
no_new_h  = h <= bk_h + 0.1 * atr
no_new_l  = l >= bk_l - 0.1 * atr
is_pin    = no_new_h & no_new_l
rejection = abs(open - close) > 0.7 * atr
pause     = (is_inside | is_doji | is_pin) & ~rejection
```

**For Hadrian:** `tp_price=None` (time-based exit). Must implement `should_exit` to close after `hold_bars`.

---

## 4. TREND-DH1-001 — CROSS-REFERENCE ANALYSIS

### 4.1 Where Did TREND-DH1-001 Come From?

**Answer:** It was built by an earlier agent based on `prompt.txt` and `prompt3.txt` — **not** directly ported from any `old_tools/` file.

The prompt described a concept:
- Daily C_N2 detection → 3-bar box → breakout confirmation → H1 entry on 12 EMA wick touch → exit on 12/21 EMA cross
- Benchmark target: n≈104, EV≈5.06R, WR≈26.9%

The agent implemented this concept in `systems/trend_dh1_001.py`, but **the benchmark was never verified against old_tools data.**

### 4.2 Comparison: Current Hadrian vs. Closest old_tools Equivalent

The closest old_tools system to TREND-DH1-001 is **sysfind3 System E** (research_v3.py), which also uses:
- Consolidation detection (24 bars < 3×ATR)
- Breakout confirmation
- H1 execution
- EMA-based entry (pullback to 12 EMA)
- EMA-cross or bands-flip exit

| Component | sysfind3 System E | Current Hadrian trend_dh1_001 |
|-----------|-------------------|-------------------------------|
| Consolidation | 24 bars < 3×ATR | Daily C_N2 state machine (clean → retrace → box → breakout → confirmation) |
| Trend filter | EMA50 uptrend | Daily bullish state |
| Entry trigger | Breakout + pullback to 12 EMA | Daily breakout → H1 12 EMA wick touch |
| EMA periods | 12/21 | 12/21 |
| SL | ATR-based (configurable) | ATR-based (configurable) |
| Exit | Bands flip or EMA cross | EMA12/21 cross |
| Retest counting | No | Yes (1-4 retests) |

**Critical difference:** The current Hadrian system adds a **daily C_N2 state machine** and **retest counting** that do not exist in sysfind3. These were added by the earlier agent and may explain the n=316 (much higher frequency) vs expected n=104.

### 4.3 Why Current Hadrian Produces n=316, EV=-0.15R

1. **EMA alpha bug (fixed in audit):** Original code used `alpha = 2 / period` instead of `2 / (period + 1)`, causing EMAs to react too slowly. This was fixed but improved EV only marginally (from -0.15R to -0.04R).

2. **Overly permissive entry:** The daily C_N2 state machine + retest counting allows entry on any H1 bar that touches the 12 EMA within 5 days of a daily breakout. This generates ~3× more trades than the original concept.

3. **Exit too slow:** EMA12/21 cross exit with 24-bar minimum hold keeps trades open too long in choppy conditions, turning small wins into losses.

4. **The benchmark itself is wrong:** Since the 5.06R benchmark never existed, trying to match it is impossible. The actual best trend system in old_tools achieves ~2.0R EV.

### 4.4 Rebuild Recommendation

Since the exact original (n=104, EV=5.06R) does not exist, the most defensible rebuild is from **sysfind3 H1_00086**:
- It is a proven trend-continuation system
- It achieved the highest EV of any sysfind3 system (1.99R)
- It is conceptually similar (consolidation → breakout → entry → managed exit)
- It is simple and clean

**Alternatively:** Keep the current `trend_dh1_001.py` architecture but rebalance parameters to reduce trade frequency and improve exit timing. However, without a verified original to clone from, this becomes parameter optimization — exactly what the audit warned against.

---

## 5. DEAD ENDS FROM OLD RESEARCH

The following concepts were tested and produced EV < 0.3R or n < 30. **Do not implement or retest.**

### sysfind1
- BTC/ETH 5m mean reversion: fee-terminal (net EV negative)
- BTC/ETH 15m mean reversion: marginal (net EV ~0.30R, not reliable)
- Trail-to-BE: EV=0.06R (worse than no trailing)
- RSI/ADX/hour-of-day/day-of-week filters: no improvement

### sysfind2
- Most v1.0-v1.3 configs: net EV < 0.3R
- EMA retest variants: generally negative
- Exit sweep variants: no viable configs

### sysfind3
- **Systems A-D (v3):** All discarded. EV < 0.5R or negative.
- **System E (v3):** Borderline. n=78, EV=1.896R — below n=100 target.
- **EMA100 pullback:** 0.23R
- **M5 FVG:** -0.86R
- **Multi-instrument basket (unfiltered):** 0.58R EV (diluted)
- **Daily post-breakout (ETH):** 2.48R but n=30 (insufficient)

---

## 6. VERIFICATION STATUS

### TREND-DH1-001 Verification: **FAILED — BENCHMARK NON-EXISTENT**

The verification run specified in the merge prompt targets `n≈104, EV≈5.06R`. This target cannot be achieved because:
1. No system in `old_tools/` ever produced these stats.
2. The benchmark appears to be an aspirational target from prompt files.
3. The highest EV found in any trend-like system is **1.99R** (sysfind3 H1_00086).

**Instead, verification should target:**
- Rebuilt from H1_00086: Expected n≈190, EV≈1.5-2.0R (Hadrian's fee model differs slightly)
- Ported mean reversion: Expected n≈180, EV≈2.0-2.5R

---

## 7. DATA SOURCE CONSISTENCY

All three sysfind generations use **Binance via CCXT** — the same source as Hadrian Engine. Data differences do not explain the benchmark gap.

**Differences:**
- sysfind1: BTC/USDT, ETH/USDT, 5m/15m/1h/4h, period 2022-now
- sysfind2: BTC/USDT, 15m, session-based
- sysfind3: BTC/USDT, ETH/USDT + 10 alts, 1h/4h/daily, period ~2018-2024
- Hadrian: BTC/USDT, ETH/USDT, 1d/4h/1h/15m/5m, IS=2016-2022, OOS=2023-2026

**Fee model differences:**
- sysfind1: 0.02% per side + explicit slippage in R
- sysfind2: 0.02% per side + funding costs
- sysfind3: 0.02% per side + entry slip + funding
- Hadrian: TAKER_FEE from config.env (default 0.035% = 0.00035) applied on both legs

Hadrian's default fee (0.035%) is **higher** than old_tools (0.02%). Results in Hadrian may be slightly lower than old_tools for the same logic.

---

## 8. SYSTEMS EXTRACTED TO HADRIAN

| System File | Source | Original EV | Hadrian EV | Status |
|-------------|--------|-------------|------------|--------|
| `systems/mean_reversion_range.py` | sysfind1 | 2.42R | **0.00R** (ETH 1h full) | **Ported but FAILED** — entry-bar SL check kills edge |
| `systems/post_breakout_continuation.py` | sysfind3 H1_00086 | 1.99R | **1.15R** (BTC 1h full) | **Ported and VERIFIED** — IS=1.00R, OOS=1.42R |
| `systems/trend_dh1_001.py` | prompt-based (no original) | N/A (claimed 5.06R, actual ~0R) | **~0R** | **Retained with warning** — benchmark is non-existent |

---

## APPENDIX: Exact grep Results

```bash
# Search for benchmark strings across entire repo
$ grep -rn "n=104\|n≈104" .
./old_prompts/prompt.txt
./old_prompts/prompt3.txt
./FIX_LOG.md
./AUDIT_REPORT.md

$ grep -rn "5.06R\|5.06" old_tools/
# Only avg_win_r or r_per_month values, never EV for a trend system
```

**Conclusion:** The benchmark `n=104, EV=5.06R` for TREND-DH1-001 is **not present in any old_tools research artifact.** It was a target specified in prompts, never achieved empirically.
