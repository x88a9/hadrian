# Engine phase (E1–E5) — plan

Restore point: tag `pre-engine-phase` at `b85eea864d111a5174e446c82df944faf96a46b9`.

The goal of this phase is to turn Hadrian³ from a store of *imported* backtest
results into a system that *produces* them: a strategy model, an event-driven
backtesting engine, an authoring surface, and an execution layer that never
touches mainnet.

---

## The non-negotiable boundary

Everything below is built inside one constraint: **this phase arms no real
mainnet trading**. The constraint is structural, not a convention:

1. `ExecutionMode` has three members. `DRY_RUN` (default, no network) and
   `TESTNET` are permitted. `MAINNET` exists as a value so the type is honest
   about the eventual target, and is refused by a guard on every path that
   could place an order.
2. There is no mainnet *exchange* base URL anywhere in the tree — not in code,
   config, `.env.example` or tests. A mainnet order cannot be addressed even if
   the guard were removed, because there is nothing to address.
3. Market data is separated from order placement. `InfoClient` is read-only,
   speaks to `/info` only, holds no key material and imports no signing
   library; it may read mainnet *candles*, because price history is data.
   `ExchangeClient` is the only thing that signs, and it is mode-gated.
4. Signing credentials are testnet-only and are read from the environment.
   No key is committed, generated into the repository, or defaulted.

Enforced by `tests/test_execution_boundary.py`, which reads the source tree
rather than calling the code, so it catches a re-introduction rather than a
misbehaviour.

---

## E1 — Strategy core & DSL  *(core)*

**E1.1 Strategy Definition.** The versioned schema both authoring paths produce
and the engine consumes. Pydantic, `schema_version` pinned, JSON-serialisable,
stored as JSONB. This lands first because everything else depends on its shape.

Contents: metadata (name, asset, timeframe), the indicator set to precompute,
entry/exit/filter rules, and a risk block (stop placement, target, sizing).
Rules are expressed as a small typed expression tree — comparisons over
indicator/price/position operands — so the visual designer can emit it and a
Python strategy can be compiled *down* to it.

*Acceptance:* round-trips to JSON and back byte-identical; an unknown
`schema_version` is refused with a clear error; invalid rule trees fail
validation rather than at engine runtime.

**E1.2 Python authoring interface.** A `Strategy` base class with `on_bar` and
declared parameters. The user writes ordinary Python against it.

*Acceptance:* a reference strategy (SMA cross) written against the interface
produces the same trades as the equivalent declarative definition.

**E1.3 Sandbox.** User Python is untrusted. It runs in a separate process with
no filesystem access, no network, a wall-clock timeout and an address-space
limit, and returns only serialised results.

*Acceptance:* tests prove that an attempt to open a file, to open a socket, to
spin forever, and to allocate past the limit each fail *inside* the sandbox and
surface as a clean, typed error — never as a hang or a partial write.

## E2 — Backtesting engine  *(core)*

**E2.1 OHLC data layer.** A `CandleSource` interface with two implementations —
the read-only Hyperliquid `/info` candle endpoint and a CSV/upload path — behind
a content-addressed local cache so a backtest is reproducible offline.

**E2.2 The engine.** Event-driven, one bar at a time. A bar is closed before it
is visible; the engine hands the strategy a view that cannot reach index > t.
Costs (entry/exit fees, slippage, funding) are applied in the same R terms the
rest of the platform uses.

**E2.3 Persistence.** Results land in the existing `systems` / `trades` tables
under a new provenance `engine`, alongside the imported `manual` /
`programmatic` systems, whose rows and metrics this phase does not touch. The
existing metrics and quant analytics apply unchanged.

*Acceptance:* a no-lookahead test — a strategy that would be trivially
profitable given one bar of future knowledge returns exactly the unprofitable
result on synthetic data with a known answer; `metrics.py`/`quant.py` unchanged
(0-byte diff) and their tests still green.

## E3 — Designer surface  *(Python path core, visual path stretch)*

Monaco editor in the frontend, strategy CRUD with versioning, backtest launched
from the UI, results rendered with the existing equity-curve / R-histogram /
quant components. The visual block designer is a second tab and is the first
thing to drop if time runs out.

## E4 — Parameter sweeps  *(only once the core stands)*

Sweeps over a strategy's declared parameters, feeding the existing
`parameter_sweeps` topography infrastructure. Batch execution with progress.

## E5 — Execution: dry-run and testnet only

Signal generation from a live strategy, position sizing through the **existing
verified** `risk_calc.compute_risk` (unchanged), stage-based scaling
(backtest → live_testing → active). `DRY_RUN` logs the order it would have
placed and touches no network. `TESTNET` places it against Hyperliquid testnet
with a testnet-only agent wallet supplied by the operator. Mainnet stays behind
the guard and is a separate, manual step outside this phase.

---

## Order of work

Boundary → E1.1 → E1.2/E1.3 → E2.1 → E2.2/E2.3 → E3 → (E4, E5, visual designer).

`main` stays runnable after every task; commits are small and path-scoped so any
single step can be reverted without unwinding the phase.
