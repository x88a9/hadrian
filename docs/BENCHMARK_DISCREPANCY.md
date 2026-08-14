# Benchmark discrepancy: TREND-DH1-001

> **Provenance.** This documents a finding from the upstream research engine
> whose results this platform ingests, not from the platform itself. The primary
> sources are archived under [`legacy/`](legacy/) and are cited by line
> throughout.

A system in this research line carried a headline benchmark of **n≈104,
EV≈5.06R, WR≈26.9%, R/yr≈62.9**. It was the reference figure that later work was
measured against, and it did not survive being checked.

---

## The rebuild

Rebuilding the system on an engine with bar-by-bar exit evaluation produced
**n=316, EV=−0.15R** — not a degraded version of the benchmark but the opposite
sign, at three times the trade count.

That gap was large enough to be a bug rather than a result, so the engine was
audited before the system was. The audit found ten defects and fixed all of them
(`legacy/FIX_LOG.md`), including three genuine lookahead errors:

- `pivot_high`/`pivot_low` used `center=True`, giving symmetric windows that
  reach into future bars. This contaminated swing detection across roughly ten
  systems.
- Two systems carried custom swing-detection helpers with the same defect.
- Three systems held module-level mutable caches that persisted across runs.

Also corrected: an EMA smoothing factor of `2 / period` instead of
`2 / (period + 1)`, a missing minimum-holding-period guard, inconsistent
annualisation between Sharpe and R/yr, and silent acceptance of truncated OHLCV
downloads.

After every fix: **n=315, EV=−0.042R** (`legacy/FIX_LOG.md`). The sign changed;
the magnitude did not. A backup of the system that already contained the correct
smoothing factors and the holding guard produced **n=291, EV=−0.07R**.

---

## Why the benchmark could not be reproduced

The audit's own verdict was that its diagnosis had been insufficient
(`legacy/FIX_LOG.md`). The search then moved from the rebuild to the benchmark
itself, and that is where it ended.

`legacy/ANALYSIS.md:13` states the result plainly:

> The benchmark quoted for `trend_dh1_001` — **n≈104, EV≈5.06R, WR≈26.9%,
> R/yr≈62.9** — **was never achieved by any system in any `old_tools/` folder.**

The supporting evidence (`legacy/ANALYSIS.md:15-23`, `:489-499`):

- The figure appears **only in prompt files** — `old_prompts/prompt.txt`,
  `old_prompts/prompt3.txt` — and in audit documents that quote those prompts.
- A repository-wide grep for `n=104` and `5.06R` returns **zero actual backtest
  output files**. Every hit is a prompt or a document citing one.
- The historical results ledger for the system records no run that ever reached
  it (`legacy/FIX_LOG.md`).
- Where `5.06` does appear in real output, it is never an EV: once as
  `r_per_month=5.0638` for a pre-fee configuration, and once as
  `avg_win_r=5.0654` for a failed trailing-stop experiment whose **actual EV was
  0.047R**.

The benchmark was an aspirational target written into a prompt, which was later
read back as a measurement.

---

## What did explain the rebuild's numbers

Separately from the benchmark's non-existence, `legacy/ANALYSIS.md:395-401`
records why the rebuild behaved as it did:

1. **The EMA smoothing bug**, fixed during the audit — worth only −0.15R → −0.04R.
2. **An over-permissive entry.** A daily state machine plus retest counting
   admits entry on any hourly bar touching the 12 EMA within five days of a
   breakout, generating roughly **three times** the trades of the original
   concept — which accounts for n=316 against an expected n≈104.
3. **An exit that is too slow.** The EMA cross exit with a 24-bar minimum hold
   keeps positions open through chop, "turning small wins into losses".
4. **The benchmark itself.** Matching a figure that was never measured is not a
   target, and the highest EV found in any comparable system in the archive was
   1.99R.

---

## Conclusion

The benchmark is not reproducible under correct backtesting, because there is no
result to reproduce. **The system is treated as unvalidated, and 5.06R is no
longer used as a target figure anywhere in this project.**

Two things follow that outlive the specific system:

**A number's provenance is part of the number.** A figure that circulates
between documents without a run behind it becomes load-bearing purely by
repetition. The check that settled this was not statistical; it was grepping for
the value in actual output files and finding none.

**Fixing the measurement first was still correct.** The audit did not recover the
benchmark, but it removed three real lookahead defects that were silently
inflating results across about ten systems. Those would have gone on corrupting
every subsequent comparison. That the investigation ended somewhere other than
where it aimed does not make the ten fixes less real.

This is also why the platform in this repository reconciles computed metrics
against reported ones on every import, at a relative tolerance of `1e-6`, rather
than trusting either in isolation.

---

## Sources

All under [`legacy/`](legacy/), archived verbatim from the upstream engine:

| File | Contains |
| --- | --- |
| `ANALYSIS.md` | The cross-reference audit that established the benchmark never existed |
| `AUDIT_REPORT.md` | The full engine audit, defect by defect |
| `FIX_LOG.md` | The ten applied fixes and the post-fix verification result |
| `COMPLETION_REPORT.md` | The 2,742-combination search and its 0.73R ceiling |
| `README_AGENT.md` | The engine's research discipline rules |
