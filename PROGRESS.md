# Progress

Running record of what is built, verified and open. Newest phase first.

---

## Wiederherstellungspunkte / Restore points

| Tag | Commit | Date | What it restores |
| --- | --- | --- | --- |
| `pre-engine-phase` | `b85eea864d111a5174e446c82df944faf96a46b9` | 2026-08-25 | State immediately before the engine phase (E1–E5): 75 imported systems, quant analytics, verified risk calculator, live-trading journal. Annotated tag, pushed to origin. |

Roll back with:

```bash
git reset --hard pre-engine-phase          # discards local work
git checkout -b rescue pre-engine-phase    # keeps main, branches from the point
```

---

## Baseline measured at the restore point

Measured on 2026-08-25 against `b85eea8`, not taken from prior notes:

- Backend suite: **326 passed, 16 skipped** (342 collected) with the dev Postgres
  up (`bash backend/scripts/dev_db.sh`). Without it, 163 pass and 179 skip —
  the integration tests skip cleanly rather than fail.
- Frontend has no test runner; `tsc` and `next build` are the gate there.

> The engine-phase brief cited 482 tests. The repository at the restore point
> collects 342. Growth is tracked from **342**.

---

## Engine phase (E1–E5) — complete

**Suite: 591 passed, 16 skipped.** `metrics.py`, `quant.py` and `risk_calc.py`
are byte-identical to the restore point (verified by hash and by `git diff`).
Migrations 0010 and 0011 verified up → down → up. Frontend `tsc` and
`next build` clean.

### The safety boundary — built first, before anything could cross it

`app/execution/mode.py` names three execution modes and permits two. **Mainnet
is refused four independent ways**, any one of which would be enough:

1. `parse_execution_mode` — the only conversion from configuration or request
   data — will not return it. No setting, environment variable or payload
   resolves to it.
2. `require_permitted` raises on every path that could place an order.
3. `EXCHANGE_BASE_URLS` has no mainnet entry. Removing the guards would produce
   a `KeyError`, not a working order.
4. **The default install has no capability to sign a transaction at all.**
   `eth-account` and `msgpack` live in `requirements-testnet.txt`, are imported
   at call time, and are absent otherwise. That is stronger than a guard: a
   guard can be removed by a refactor, a missing library cannot.

`tests/test_execution_boundary.py` (26 tests) reads the *source tree* rather
than calling the code, because the thing being protected is an invariant of the
repository rather than a behaviour of today's build.

Reading mainnet candles is deliberately not execution. `HyperliquidInfoSource`
refuses any URL whose path is not `/info`, holds no key material and imports
nothing that can sign. Without that split the boundary would have had to choose
between being strict and being usable.

### E1 — Strategy core, Python interface, sandbox ✅

- **Strategy Definition** (`app/strategy/definition.py`, 42 tests). Versioned,
  JSONB-serialisable, validated eagerly. Rules are a typed expression tree in
  which every operand carries a non-negative bar offset, so **lookahead is
  unrepresentable** rather than merely avoided.
- **Two rule carriers, one definition.** `rules="declarative"` uses the tree;
  `rules="python"` puts the logic in `python_source`. Metadata, indicators,
  risk, costs and parameters are shared, which is what makes a hand-written
  strategy sweepable and a designed one storable by the same code.
- **Python interface** (`app/strategy/interface.py`). Stdlib only — everything
  the sandbox imports is surface untrusted code can reach.
- **Sandbox** (`app/strategy/sandbox.py`, 37 tests that attack it). Four
  layers: an unprivileged user+network namespace where the kernel allows one,
  `sys.addaudithook`, rlimits, and a wall clock that kills the process group.
  Tests prove that reading `/etc/passwd`, opening a socket, spawning a process,
  loading `ctypes`, looping forever and allocating past the limit all fail
  inside.

### E2 — Backtesting engine and data layer ✅

- **Data sources** (62 tests, none touching the network). Read-only `/info`
  candles, CSV/upload, and a content-addressed cache with an `offline` mode.
- **Engine** (`app/engine/`, 30 tests). Event-driven; a signal on bar *i* fills
  at the open of bar *i+1*. A bar touching both stop and target takes the stop;
  a gap fills at the open, in both directions rather than only the flattering
  one.
- **Persistence.** Results land in the existing `systems`/`trades` tables under
  provenance `engine`, so the existing metrics, walk-forward and Monte-Carlo
  read them with no special-casing. `materialise_system` **refuses outright** to
  touch a system whose provenance is not `engine`.

### E3 — Designer surface ✅ (including the visual block designer)

Monaco editor with Python highlighting, strategy CRUD, append-only versioning,
duplication, backtest from the UI rendered through the existing metric cards,
equity curve and R histogram, and a trades table. Warnings are shown
prominently rather than buried.

**The block designer** is a second tab editing the *same* `StrategyDefinition`
object as the JSON editor — one object, two windows, one save path. Its palette
is served by `GET /strategies/schema`, derived from the Python `Literal` types
and the indicator registry rather than duplicated in TypeScript, so it cannot
drift: a test asserts the derivation stays total in both directions.

Verified against the running API rather than only against itself:
`frontend/lib/blocks.contract.test.ts` round-trips a definition through the
helpers and posts it to the real validator, and checks that switching to a
crossing comparator strips the offsets the backend would otherwise reject. It
skips cleanly when the API is down.

### E4 — Parameter sweeps ✅

Two declared parameters swept over their declared ranges into the existing
topography. Bars fetched once; a Python strategy's whole grid runs in a single
sandbox process. Synchronous, bounded at 400 cells.

### E5 — Execution: dry-run and testnet ✅ (with one caveat, below)

Sizing goes through the **verified** `compute_risk`, with stage scaling applied
via its own `risk_modifier` so the arithmetic stays inside the verified module.
The reference case still lands on 0.00312 / 340.08 / 3.00388608 through the new
path. `backtest` and `retired` raise rather than sizing to zero;
`live_testing` takes a quarter. Every order is journalled — dry runs as
completely as real ones, and never with a venue order id.

---

## Verified end to end, against live read-only market data

2880 real BTC 1h bars fetched through the `/info` client; 22 trades, +10.81R,
grade C; materialised as an engine system that `/systems/{id}/montecarlo` and
`/systems/{id}/walkforward` read with no special-casing.

---

## Open / not verified

1. **The testnet signature has not been exercised against the live venue.**
   Everything around it — mode gating, credential handling, order construction,
   response reading — is tested through `httpx.MockTransport`. The signing
   scheme is implemented from Hyperliquid's documented L1-action format, but
   verifying it needs a funded testnet agent wallet, which is the operator's to
   create and is deliberately not committed. A wrong signature is rejected by
   the venue rather than filling something unintended. **Treat the first live
   testnet order as the acceptance test.**
2. **The block designer has no browser-level test.** Its pure logic has unit
   tests and its schema agreement has contract tests, but the React components
   are covered only by `tsc`, the production build, and a page-load smoke test.
   Nobody has automated a click-through.
3. **Sweeps are synchronous and capped at 400 cells.** A larger grid wants a
   job queue. Building one before a sweep needs it would be machinery in front
   of a wait nobody has yet noticed.
4. **The candle cache cannot distinguish "queried and legitimately empty" from
   "never queried"**, so such a range is re-fetched each time. Documented in
   `app/data/cache.py`; solving it needs a coverage record independent of the
   bars.
5. **`walkforward` on a short engine backtest returns zero windows.** Correct
   behaviour — 120 days is shorter than the default 6+3-month window — but
   worth knowing before reading it as a failure.

## Assumptions taken

- **Repository documentation stays in English** (matching `README.md` and
  `docs/DECISIONS.md`), while conversation with the operator is in German.
- **Engine trades classify their own outcome.** A trade closing at -0.05R is a
  loss, where `metrics.derive_win_loss` returns `None` because the research
  workbook left that cell blank. Documented in `docs/DECISIONS.md` and pinned
  by tests on both halves.
- **Stage scaling is 0 / 0.25 / 1.0.** Deliberately coarse; a finer schedule
  would imply a precision about the stage-to-confidence relationship that
  nothing here measures.
- **A backtest starts two years back** when no range is given.
- **`CandleSeries` allows gaps but records them.** Refusing them outright would
  make thin markets unbacktestable.

## Corrections made to the brief's premises

- **There was no Hyperliquid integration to preserve.** The brief described a
  read-only `/info` binding as existing and test-covered. `backend/app/`
  contained zero outbound HTTP; `app/models/account.py` said so explicitly. The
  binding was built in this phase, with the boundary designed in from the start.
- **The suite was 342 tests, not 482.**
- **`CLAUDE.md`, `TASKS.md` and `PROGRESS.md` did not exist.** The latter two
  were created; there is still no `CLAUDE.md`.

## The next step toward mainnet — separate and manual

Not something this phase can do, and deliberately not something a refactor can
do quietly. In order:

1. **Exercise the testnet path.** Generate a throwaway testnet agent wallet,
   fund it from the faucet, put the key in your own `.env` as
   `HL_TESTNET_AGENT_KEY`, install `requirements-testnet.txt`, set
   `EXECUTION_MODE=testnet` and place one order. This is the acceptance test
   for the signature.
2. **Run a strategy in `DRY_RUN` for long enough to compare** the journal
   against what the testnet then actually did.
3. **Only then**, as one deliberate reviewed change: add the mainnet exchange
   URL to `EXCHANGE_BASE_URLS`, add `MAINNET` to `PERMITTED_MODES`, pass
   `allow_mainnet=True` at the single call site, and update
   `tests/test_execution_boundary.py` — which will fail loudly first, by
   design. That failing test is the point at which someone has to decide, on
   purpose, that this build trades real money.
