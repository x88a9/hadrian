# HADRIAN ENGINE — YOLO SESSION COMPLETE

**Date:** 2026-05-13
**Total runs logged:** 3,335
**Unique combos tested:** 2,742
**New systems written:** 9 (A through I)

---

## VALIDATED (EV > 0.8R OOS, degradation < 30%)

**None.**

No system configuration reached the 0.8R IS threshold required to trigger OOS validation.

---

## PROMISING (EV > 0.8R IS, OOS not yet run or weak confirmation)

**None.**

The highest IS EV achieved was 0.7289R — below the 0.8R promising threshold.

---

## BORDERLINE (EV 0.3–0.8R, n >= 30)

| Rank | System | Config | EV(R) | WR% | n | MaxDD(R) | R/yr |
|------|--------|--------|-------|-----|---|----------|------|
| 1 | candle_structure | engulfing_bull_dc_highlow_SLatr1.0_TPfixed_r2.0_Eclose | 0.7289 | 58.1 | 31 | 6.08 | 3.72 |
| 2 | bollinger_band_structure | S3_BB20x2.0_W3_SLatr1.0_TPfixed_r2.0_Eclose | 0.7262 | 58.1 | 31 | 6.08 | 3.72 |
| 3 | ma_relationship_breakout | S5_ema50_SL3_SLatr1.5_TPfixed_r3.0_Eclose | 0.7226 | 43.3 | 30 | 13.25 | 1.82 |
| 4 | candle_structure | engulfing_bull_dc_highlow_SLatr1.0_TPfixed_r3.0_Eclose | 0.7177 | 43.3 | 30 | 6.08 | 3.72 |
| 5 | bollinger_band_structure | S3_BB20x2.0_W3_SLatr1.0_TPfixed_r3.0_Eclose | 0.7174 | 43.3 | 30 | 6.08 | 3.72 |
| 6 | candle_structure | engulfing_bull_anywhere_SLatr1.0_TPfixed_r3.0_Eclose | 0.6102 | 50.0 | 32 | 4.08 | 4.27 |
| 7 | bollinger_band_structure | S6_BB20x2.0_W20_SLatr1.5_TPfixed_r3.0_Eclose | 0.6589 | 43.6 | 39 | 9.17 | 4.20 |
| 8 | swing_structure | G_pivot2_sc1_SLatr1.0_TPfixed_r3.0_Eclose | 0.5624 | 39.4 | 71 | 9.53 | 4.27 |
| 9 | vwap_structure | S4_session_SL5_SLatr1.5_TPfixed_r3.0_Eclose | 0.5663 | 40.0 | 55 | 8.04 | 2.15 |
| 10 | altcoin_cross_asset | SA1_SLatr1.5_TPfixed_r3.0_Eclose | 0.4506 | 37.1 | 62 | 15.58 | 4.27 |

---

## CROSS-TF / CROSS-ASSET TESTS (top configs)

| Config | TF | Symbol | EV(R) | n | Status | Notes |
|--------|----|--------|-------|---|--------|-------|
| F engulfing_bull_dc | 4h | BTC | 0.0706 | 192 | DEAD END | Severe degradation from 1d |
| B S3_BB20x2.0_W3 | 4h | BTC | 0.2146 | 258 | DEAD END | Degraded from 1d |
| A S5_ema50_SL3 | 4h | BTC | 0.1502 | 206 | DEAD END | Degraded from 1d |
| F engulfing_bull_dc | 1d | ETH | -0.0449 | 31 | DEAD END | Negative on ETH |
| B S3_BB20x2.0_W3 | 1d | ETH | 0.5767 | 34 | BORDERLINE | Best risk metrics (PF=2.21, MDD=3.03R) |
| A S5_ema50_SL3 | 1d | ETH | 0.4039 | 25 | INCONCLUSIVE | n<30 |

---

## STRUCTURAL FINDINGS

### Which indicator families showed any edge above 0.3R EV?
1. **Candle patterns at key levels** (System F) — engulfing_bull at Donchian extremes produced the highest EV (0.73R). Hammer patterns at anywhere also reached 0.61R.
2. **Bollinger Band walking-the-bands** (System B, S3) — consecutive closes beyond BB bands reached 0.73R.
3. **MA slope change** (System A, S5) — EMA50 slope turning positive after lookback produced 0.72R.
4. **Swing structure breaks** (System G) — simple pivot2 breaks with minimal confirmation reached 0.57R.
5. **VWAP slope** (System C, S4) — session VWAP slope changes reached 0.57R.

**Consistently negative families:** Volume climax reversals (System E S4), CVD/OBV divergences (System E S1/S2), dry-up breakouts (System E S5), most mean-reversion fades.

### Which signal types were consistently negative across all params?
- **Volume climax reversals** (S4) — strongly negative EV across all volume thresholds and wick multipliers.
- **CVD divergence** (System E S2) — negative or near-zero EV on all parameter sets.
- **Donchian false breakout** (System D S2) — consistently negative.
- **BB midline cross** (System B S5) — near-zero to negative.
- **Multi-indicator confluence** (System H) — underperformed single-indicator equivalents; the hypothesis that confluence improves EV was **rejected** by the data.

### Which TF/asset combinations showed best signal quality?
- **1d BTC** was the dominant source of edge. Every system that produced borderline results did so on 1d BTC.
- **4h BTC** degraded all top configs to dead-end territory (EV < 0.22R).
- **ETH 1d** showed mixed results: BB walking-the-bands reached 0.58R with excellent risk metrics, but candle patterns went negative.

### What confluence pattern came closest to the 1.2R threshold?
**None came close.** The best confluence pattern (System H C4: engulfing + MA direction) reached only 0.43R. The hypothesis that combining 2-3 signals reduces false positives enough to cross 1.2R was **rejected**.

### Any cross-asset signal that outperformed single-asset version?
**No.** The ETH version of the top BB config reached 0.58R vs 0.73R on BTC. The ETH version of the candle pattern went negative. BTC remains the superior signal source.

---

## VS BENCHMARK (TREND-DH1-001)

Benchmark: EV=5.06–8.22R | R/yr=41–63 | WR=27–55%

**Closest system found:** candle_structure engulfing_bull_dc_highlow at 0.73R EV.

**Gap to close:** 5.9R EV (8× improvement needed) or ~58 R/yr.

The entire indicator library tested (MA, BB, VWAP, DC, volume, candle patterns, swing structure, confluence) sits in a **0.3–0.7R EV band** on BTC daily. None approach the benchmark's 5R+ EV. This suggests either:
1. The benchmark exploits a different signal class (e.g., regime detection, macro correlation, halving cycles), or
2. The benchmark was optimized on data not available to these systems, or
3. The true edge lies in **position sizing / risk management** rather than entry signals.

---

## WHAT TO TRY NEXT

### Immediate tactical ideas
1. **Regime-dependent switching:** The 0.7R ceiling might be broken by only trading when ATR_ratio > 1.2 (trending regime) for trend signals, and ATR_ratio < 0.8 (ranging) for mean-reversion signals. Test the top 3 configs with ATR regime filter.
2. **Higher-complexity swing detection:** System G's pivot2 break showed 0.57R. Test fractal-based or ZigZag-based breaks with 3-5 point confirmation.
3. **Session/time-based filtering:** The UTC daily open and macro event windows (FOMC, CPI) were not tested. BTC shows behavioral shifts around these times.

### Structural unlocks
4. **On-chain data:** The prompt restricts to TradingView-visible indicators, but if that constraint is lifted, exchange flows, funding rates, and liquidation clusters are the most likely source of the benchmark's edge.
5. **Options market data:** Implied volatility skew and delta positioning encode institutional directional bias not visible in OHLCV.
6. **Cross-asset lead-lag with lag optimization:** System I tested fixed lags (1-3 candles). A dynamic lag based on rolling correlation might capture the true BTC-alt lead-lag relationship.

### Abandoned branches (do not pursue)
- Volume climax reversals (System E S4) — consistently negative across all parameters.
- Multi-indicator confluence (System H) — underperformed single-indicator systems.
- BB %B extremes (System B S2) — near-zero EV, no edge.
- Donchian false breakout (System D S2) — consistently negative.

---

## ANTI-FALLACY CHECKLIST

- [x] No lookahead in any get_signals function
- [x] Entry timing = close or next_open only
- [x] Fees from config.env (TAKER_FEE=0.00035)
- [x] IS dates only for all baseline runs
- [x] n >= 30 before judgment on all reported results
- [x] No overlapping trades (engine enforced)
- [x] All configs uniquely labeled

---

*Session terminated by exhaustion of research queue. No critical errors encountered.*
