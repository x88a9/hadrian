# Fix Log — Hadrian Engine Audit Fixes

| Date | File | Change | Reason |
|------|------|--------|--------|
| 2026-05-15 | systems/trend_dh1_001.py | Changed alpha12 from 2/21 to 2/13 and alpha21 from 2/51 to 2/22 | Bug: alphas implemented 20/50 EMA instead of documented 12/21 EMA |
| 2026-05-15 | systems/trend_dh1_001.py | Added 24-bar minimum holding period guard in should_exit | Bug: EMA cross exit allowed before 24 bars, causing whipsaws and fee bleed |
| 2026-05-15 | core/indicators.py | Replaced center=True pivot_high/pivot_low with right-edge-only loop | Bug: center=True caused lookahead, contaminating swing detection across ~10 systems |
| 2026-05-15 | systems/cvd_divergence_breakout.py | Replaced _is_swing_low/_is_swing_high with ind.pivot_low/ind.pivot_high | Bug: custom swing functions used future data via symmetric windows |
| 2026-05-15 | systems/higher_high_lower_low_break.py | Replaced _find_pivots custom lookahead with ind.pivot_high/ind.pivot_low | Bug: _find_pivots used future bars in swing detection |
| 2026-05-15 | systems/altcoin_momentum_vs_btc.py | Replaced module-level _BTC_DAILY_CACHE with functools.lru_cache | Bug: module-level mutable state persisted across backtest runs |
| 2026-05-15 | systems/ema_pullback_trend_filter.py | Replaced module-level _HT_CACHE with functools.lru_cache | Bug: module-level mutable state persisted across backtest runs |
| 2026-05-15 | systems/multi_tf_momentum_alignment.py | Replaced module-level _PRECOMPUTED with functools.lru_cache | Bug: module-level mutable state persisted across backtest runs |
| 2026-05-15 | core/metrics.py | Changed Sharpe sqrt(252) to sqrt(365) and R/yr denominator to 365 | Bug: Sharpe and R/yr used inconsistent annualization assumptions |
| 2026-05-15 | core/data_loader.py | Added stale/incomplete CSV detection and re-fetch with fallback | Bug: interrupted fetches produced silently incomplete cached data |

---

## VERIFICATION RESULT

VERIFICATION FAILED after all audit fixes applied.
Result: n=315 EV=-0.0421R R/yr=-1.53
Remaining discrepancy: EV is -0.84R vs expected +5.06R (delta = -5.10R, >20% tolerance). R/yr is -1.53 vs expected 62.9 (delta = -64.43, >20% tolerance).
Suspected cause: The audit's diagnosis (wrong EMA alphas + missing 24-bar guard) was insufficient. The backup file (trend_dh1_001_backup.py), which already contained correct alphas and the 24-bar guard, also produces failed results (n=291, EV=-0.07R). The historical results ledger for trend_dh1_001 shows no run ever achieved the quoted benchmark (n≈104, EV≈5.06R). The benchmark target in the audit appears to reference a version of the system that is not present in the repository. Additional structural bugs in the system's entry/exit logic (e.g. retest counting, breakout confirmation, or phase machine state transitions) remain undiagnosed.
