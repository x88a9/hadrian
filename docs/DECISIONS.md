# Design decisions

Decisions that are not obvious from the code, with the reasoning that produced
them. Source files reference the section headings here.

---

## Metric formulas

Ported verbatim from the formulas in the research workbook, so that imported
figures and computed figures can be reconciled cell by cell. All metrics are
R-based and net of costs.

| Metric | Definition |
| --- | --- |
| `win_rate` | wins / total trades |
| `ev` | `AVERAGE(R)` |
| `total_r` | `SUM(R)` |
| `avg_win_r` / `avg_loss_r` | `AVERAGEIF(R > 0)` / `AVERAGEIF(R < 0)` |
| `total_trades` | count of rows with a non-empty entry price |
| `wins` / `losses` | count of `W/L == "Win"` / `"Loss"` |
| `ece` | `AVERAGE(R) / STDEV.S(R)` — sample stdev, ddof=1 |
| `evol` | `ev × (total_trades / span_days)` — the frequency weight is trades per day |
| `composite_score` | `0.4·ev + 0.4·ece + 0.2·evol`, on raw values, no normalisation |

Grade thresholds are the workbook's `IFS` cascades, ported exactly:

| Grade | Thresholds |
| --- | --- |
| Composite | A ≥ 0.6 · B ≥ 0.45 · C ≥ 0.3 · D ≥ 0.15 · else F (no A+) |
| EV, applied to `0.8 × ev` | A+ ≥ 0.8 · A ≥ 0.6 · B ≥ 0.4 · C ≥ 0.25 · D > 0 · else F |
| ECE | A+ ≥ 0.7 · A ≥ 0.5 · B ≥ 0.35 · C ≥ 0.2 · D > 0 · else F |
| EVol | A+ ≥ 0.4 · A ≥ 0.25 · B ≥ 0.15 · C ≥ 0.07 · D > 0 · else F |

Per-trade win/loss derivation follows the workbook: win if `R > 0`, loss if
`R < -0.1`, draw if `R == 0`. The band `-0.1 ≤ R < 0` is left blank in the
workbook; the importer takes the `W/L` cell value when present and falls back to
this rule otherwise.

**Metrics are computed on the fly, never persisted.** The header figures from
the workbook are stored separately as `reported_metrics` (JSONB) and used only
for display and reconciliation. Two independent numbers that must agree are
worth more than one number stored twice.

---

## Two tab layout variants

The research workbook grew over years and contains two layouts:

- **Variant A** (majority) — system name in `B2`, metric header in row 7, values
  in row 9. Trade header in row 13:
  `# | Day | Date & Time | Zone | Timeframe | Entry ($) | Stop Loss ($) | Exit ($) | (blank) | Direction | R | W/L`
- **Variant B** (older tabs) — system name in `B3`, metric values in row 8. The
  trade log sometimes uses `Duration | Date Start | Date End` instead of
  `Day | Date & Time | Zone`, which shifts Direction/R/W-L into columns I/J/K.

**Decision:** parse by header *text*, not by fixed coordinates. The importer
locates the trade header row by finding `#` in column A and maps columns from
their header labels; the metric row is the first non-empty row beneath the
`Composite Grade` header; the name comes from `B2`, then `B3`, then the sheet
name. For variant B, `Date Start` is the trade date and `Date End`/`Duration`
are ignored.

**Why:** fixed coordinates failed on roughly seven real tabs. Header matching
handles both variants without special-casing either.

---

## Broken and unfinished tabs

Real workbooks contain unfinished backtests. Four error classes were observed:
`#DIV/0!` confined to EVol/Composite (empty date column, so the span is zero)
while EV/ECE remain valid; entirely `#N/A` headers with no numeric R values;
scattered `#REF!` in trade cells; and mini-tabs with fewer than five trades and
no metrics at all.

**Decision:** the importer never crashes. Error sentinels (`#DIV/0!`, `#N/A`,
`#REF!`, …) become `None`. A system is imported as `import_status=complete` when
at least one trade carries a numeric R value, otherwise `incomplete` — with the
system, its rules and whatever trades parsed still persisted. Every tab outcome
is recorded in the `ImportRun` log, so a skipped tab is visible rather than
silent.

---

## Import idempotency

**Decision:** upsert by system name (unique). A re-import replaces a system's
trades wholesale — delete plus insert in one transaction — rather than matching
individual rows.

**Why:** the workbook is the source of truth for manual backtests, and trade
rows have no stable natural key. Wholesale replacement is deterministically
idempotent and easy to keep correct. Trades from other sources are untouched:
the xlsx import only replaces `source=manual` trades.

### Re-import protection

User data always wins over import data. Enforced in three layers:

1. **`systems.origin`** (`import` | `ui`) — `POST /systems` marks anything
   created through the UI as `origin='ui'`, and both importers skip such systems
   entirely, logging them visibly as skipped rather than passing over them
   quietly.
2. **`systems.user_overrides`** (JSONB list of field names) — fields edited in
   the UI on an imported system (`entry_rule`, `sl_rule`, `tp_rule`, `notes`,
   `timeframe`, `asset`) are left alone by the re-import upsert.
3. **`source`** on trades — the importer only ever replaces trades that it
   created itself.

CSV import remains allowed for trades, since that is an explicit per-system
action, but it no longer touches fields of existing systems.

---

## Name collision between tab and system name

The tab `TREND-WH4-801.A` carries the system name `TREND-WH4-801` in `B3` —
identical to the standalone tab of that name. Both resolve to one system, so 44
tabs yield 43 distinct systems.

**Decision:** follow the naming rule literally and upsert by name. Both tabs
appear in `tab_results`, but the one processed second overwrites the first one's
trades.

**Why:** one name means one system is the simple, deterministic contract. The
`.A` variant is a duplicate experiment of the same system, the data loss is a
single trade row, and the import stays idempotent across runs. Documented rather
than silently special-cased.

---

## IS/OOS split

**Decision:** the split date is configurable via `IS_OOS_SPLIT_DATE`, defaulting
to `2024-01-01` — in-sample through 2023-12-31, out-of-sample from 2024-01-01.
Metrics are computed per system for `all`, `is` and `oos`.

Out-of-sample EV is the figure that matters. In-sample is context only.

---

## System status

**Decision:** every imported system starts at `status=backtest`. Transitions
through `live_testing` → `active` → `retired` happen manually via
`PATCH /systems/{id}`.

**Why:** the workbook carries no status information, and inferring a lifecycle
stage from performance figures would be exactly the kind of quiet assumption
this platform exists to avoid.

---

## Best-config selection for engine imports

The Hadrian Engine writes one row per parameter configuration. The importer
deduplicates by configuration label and, among the survivors, prefers a
configuration that has an out-of-sample run over one with a higher in-sample EV
but no OOS run.

**Why:** picking the highest in-sample EV is how a research pipeline talks
itself into overfitted parameters.

---

## Position sizing rounds, it does not floor

**Decision:** the position-size adjustment to the exchange's lot size is `ROUND`,
not `floor`.

**Why:** flooring systematically undersizes every position by up to one lot. The
benchmark used to validate the risk calculator was the wrong reference here, not
the code — verified against the venue's own sizing behaviour before changing it.

Three leverage concepts are kept strictly separate: *implied* leverage (position
notional ÷ account equity), *required* leverage (what the venue must be set to),
and *exchange* leverage (the integer value actually sent). Conflating them was
the source of an earlier sizing bug.

---

## Client library has no pandas dependency

**Decision:** `bulk_import` accepts a duck-typed object with `.to_csv()` (such as
a DataFrame) as well as `str`, `Path` or `bytes`. `httpx` is the only hard
dependency; pandas is available as a `[pandas]` extra.

`log_trade` is deliberately append-only with no deduplication, because a single
trade has no stable natural key. The idempotent path is `bulk_import`.

---

## Ledger is append-only

Account balance changes are never edited or deleted. Deleting a trade writes a
compensating `trade_delete` row; correcting a result writes a `trade_correction`
row. The trade's ID is recorded in the note text and the foreign key is
`SET NULL`, so a deleted trade cannot orphan or alter ledger history.

**Why:** an additive-only ledger that permitted deletion of the underlying trades
would silently corrupt the running balance. This was found in review, not in
design.

---

## Development database

**Decision:** portable zonky.io embedded PostgreSQL 16 binaries via
`backend/scripts/dev_db.sh` (port 55432, idempotent, no root required). Not
SQLite.

**Why:** `pgserver` has no cp314 wheel for Python 3.14. Testing against a
different database engine than production would defeat the purpose of the
integration tests, several of which depend on PostgreSQL-specific JSONB
behaviour.

The Docker image pins Python 3.12 for guaranteed wheel availability while local
development runs on 3.14, so no 3.13+-only syntax is used.

---

## Reconciliation tolerances

Numeric metrics are compared at relative tolerance `1e-6` (absolute `1e-9` near
zero). Counts and grades must match exactly. Cross-checks against the upstream
engines' own audit output use absolute tolerances instead, because those figures
are themselves rounded on export.

---

## The execution boundary

The engine phase builds order execution but arms no mainnet trading, and the
refusal is structural rather than a convention anyone has to remember.
`ExecutionMode` names three modes and permits two. Mainnet is refused four
independent ways: `parse_execution_mode` will not return it from any
configuration or payload, `require_permitted` raises on every path that could
place an order, `EXCHANGE_BASE_URLS` has no entry to send it to, and no signing
credential is committed or defaulted. Removing the guards would not produce a
working mainnet order — it would produce a `KeyError`.

`allow_mainnet=True` exists as a single named token so that the eventual,
deliberate arming change is a one-line diff at one call site rather than a
rewrite of the module. Nothing in the repository passes it, and
`tests/test_execution_boundary.py` reads the source tree to keep it that way.
That test asserts an invariant of the repository, not a behaviour of the
current build, which is why it greps rather than calls.

Market data is deliberately not execution. `InfoClient` reads mainnet candles
freely — price history is data, and testnet has none worth backtesting — while
holding no key material and refusing any URL whose path is not `/info`. Without
that split the boundary would have had to choose between being strict and being
usable.

## Engine trades classify their own outcome

`metrics.derive_win_loss` reproduces the research workbook's fallback rule,
under which a trade with `-0.1 <= R < 0` classifies as *nothing at all*: the
cell was left blank in the spreadsheet, and the importer has to reproduce that
to reconcile against the workbook's own figures.

The engine does not inherit that. It watched the trade close below its entry
and records a loss. Carrying a blank-cell quirk into generated results would
leave small losses unclassified and quietly undercount `losses` for every
engine-produced system. Outside that band the two rules agree exactly, and both
halves — the agreement and the divergence — are pinned by tests so neither can
drift into being accidental.

## Testing for lookahead: what does not work

The obvious property is truncation invariance: trades that finished before bar
*k* should not change when bars from *k* on are removed. It is a real property
and worth keeping, but on its own it does not catch a one-bar lookahead. A
trade that closed before *k* made its last decision at *k-2* or earlier, so it
never reads the bar the truncation removed. The test passes with the defect
present.

What does work is tampering rather than truncating, comparing decisions rather
than trades, and sweeping the cut point across every bar. Everything from bar
*k* onward is replaced with a different price path, and the strategy's decision
at *k-1* must not move. Decisions rather than trades, because a fill
legitimately depends on the bar after the decision and comparing trades would
confuse that with a defect. Every bar in turn, because a single cut point
exposes exactly one decision, which is usually nowhere near the rule's
threshold.

`test_the_lookahead_property_would_catch_a_real_defect` injects the defect and
asserts the check breaks. A property test that cannot fail proves nothing, and
this one was silently vacuous in both of its earlier formulations.
