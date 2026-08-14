# Regime selectivity via hidden Markov models

> **Status: not implemented. This is a research agenda, not a result.**
> Nothing here has been backtested. No figure below is a measurement except
> where it cites the archived search results under
> [`../../docs/legacy/`](../../docs/legacy/).

---

## Starting point: an exhausted search

The upstream research engine ran an exhaustive parameter search across nine
systems. From `legacy/COMPLETION_REPORT.md`:

| | |
| --- | --- |
| Runs logged | 3,335 |
| Unique combinations tested | 2,742 |
| Configurations reaching the 0.8R in-sample threshold | **none** |
| Highest in-sample EV achieved | **0.7289R** |
| Configurations validated out-of-sample | **none** |

The ceiling held across unrelated system families — candle patterns at Donchian
extremes reached 0.7289R, Bollinger band-walking reached 0.73R, and the best
cross-asset variant of the top configuration degraded from 0.73R on BTC to 0.58R
on ETH.

Two thousand seven hundred combinations arriving at the same ceiling from
different directions is itself the finding. It says the limit is not in the
indicators. Adding a 2,743rd combination is not a plan.

**Working conclusion:** the constraint is *when* these systems trade, not *what*
they trade on. A system with a genuine but conditional edge, run
unconditionally, reports the blend of its good and bad conditions — which is
roughly what a 0.73R ceiling with no out-of-sample survivor looks like.

---

## Hypothesis

Crypto perpetual markets pass through latent states that are not directly
observable but do leave traces across several instruments at once — positioning,
funding cost, and realised volatility move together in ways that differ by
regime.

A hidden Markov model is a reasonable fit for that shape: it assumes an
unobservable state sequence with Markov transitions, emitting observable
features whose distribution depends on the current state. If such states exist
and are separable from the features below, then filtering an existing system to
trade only in statistically favourable states should raise its expectancy above
what the unconditional version achieves.

**Target:** EV > 1.5R on a system whose unconditional version sits near the 0.73R
ceiling. Chosen because it is roughly double the ceiling — large enough that it
cannot be explained by the reduction in sample size alone.

### Planned feature set

| Feature | Rationale |
| --- | --- |
| Open interest, and its rate of change | Positioning build-up versus unwind |
| Funding rate, level and sign persistence | Directional crowding and its cost |
| Realised volatility over a rolling window | The most direct regime proxy |
| OHLCV-derived: range expansion, volume distribution | Structural context |

Features are deliberately cross-sectional rather than another price transform.
The point of the exercise is to condition on information the 2,742-combination
search never had access to.

### Planned setup

- **3–5 hidden states.** Below three cannot express more than
  trending/not-trending; above five risks states too sparse to estimate on the
  available history.
- Gaussian emissions initially, with the caveat that crypto return
  distributions are not Gaussian and this may need revisiting.
- Evaluation as a **filter** over existing systems first, since that isolates
  the regime contribution against a known baseline.

---

## Open questions

1. **How many states?** Selection criteria (BIC, held-out likelihood) optimise
   fit, not trading outcome, and the two can disagree. Choosing the state count
   by backtest performance is parameter mining with extra steps.
2. **Filter or standalone?** As a filter the contribution is measurable against
   a baseline. As a standalone signal generator it is a larger claim and a
   harder one to attribute.
3. **Which features actually carry the state?** Open interest and funding are
   correlated; including both may add noise rather than information. This needs
   settling before the model is fitted, not after seeing which combination
   backtests best.
4. **How often to retrain, and on what window?** Too rarely and the states go
   stale; too often and each fit sees too little data.
5. **Is the state count stable across assets?** If BTC needs four states and ETH
   needs three, that is either a real structural difference or a sign the model
   is fitting noise.

---

## Known pitfalls

These are the reasons this is written down before anything is implemented.

### Viterbi decoding looks into the future

The Viterbi algorithm finds the most likely state sequence **given the entire
observation sequence**. Every label it assigns to bar *i* is informed by bars
*i+1 … n*.

Running Viterbi across the whole dataset and then backtesting against those
labels is therefore not a backtest. At every historical bar the strategy would be
acting on a regime label that could not have been known at the time, and the
result will look excellent for exactly that reason.

The correct construction is filtered inference: at bar *i*, the state estimate
uses only observations up to *i*. Concretely, and matching the engine's own
discipline rules in `legacy/README_AGENT.md`:

- The model is trained only on `df.iloc[:i]` to predict the state at bar `i`.
- Feature normalisation uses rolling statistics from the training window only —
  a global mean and standard deviation leak the entire distribution.
- State labels are realigned after every retrain.
- No hyperparameter is chosen by looking at out-of-sample data, including
  informally.

The same trap has a non-HMM form worth naming, because it is easy to walk into
while thinking the HMM is the risky part: fitting *any* unsupervised model
across a full series and then labelling retrospectively has identical lookahead,
with none of the sequence machinery to make it obvious.

That is not hypothetical here. The archived predecessor project
[edge-lab](https://github.com/x88a9/edge-lab) contains a regime detector
(`analytics/regime_detection.py`) that fits k-means over rolling volatility and
mean across the entire trade series, then returns labels for that same series.
Any backtest conditioned on those labels would be acting on information that did
not exist at the time. It is the concrete version of the mistake this section
exists to prevent, which is part of why that project was archived rather than
carried forward.

### There is no ground truth

Regime detection is unsupervised. There is no labelled dataset of "this was a
trending regime" to validate against. The model will always return states — on
real data, on shuffled data, and on noise. Their existence proves nothing.

This has a direct consequence for how success is judged: an improvement in
expectancy on the filtered system is the only evidence available, which means
the usual overfitting discipline applies with more force than usual, not less.

### The sample-size trap

A regime filter that removes 70% of trades will produce a higher EV on almost
any system, because it selects a subset. The comparison that matters is not
filtered EV versus unfiltered EV. It is whether the filter beats **randomly
removing the same proportion of trades**, repeated enough times to give a
distribution. Without that null, a regime filter is indistinguishable from
having got lucky with a smaller sample.

### Regimes may be real and still unusable

The states can be statistically sound, persistent, and correctly detected in
real time, and the edge can still fail to survive costs — or the transitions can
arrive too late to act on. Detecting a regime and profiting from one are separate
claims, and only the second one matters here.

---

## Status

Not implemented. No model has been fitted, no backtest has been run, and no
result exists to report. This document records the reasoning and the constraints
so that the work, when it happens, is measured against what was planned rather
than against what turned out to be convenient.

Planned first step: assemble the feature set with strictly causal construction
and verify on synthetic data with known injected states that filtered inference
recovers them — before any trading logic is attached.
