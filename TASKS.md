# Tasks

## Engine phase (E1–E5) — complete

Restore point: `pre-engine-phase` at `b85eea8`. Plan: `docs/engine-phase-plan.md`.

| # | Task | State | Commit |
| --- | --- | --- | --- |
| B | Execution boundary: mode gate, mainnet refusal, source-level test | done | `fed6ad4` |
| E1.1 | Strategy Definition — versioned schema, two rule carriers | done | `4210bb3` |
| E1.2 | Python authoring interface (`Strategy`, `Context`, `Signal`) | done | `c71403f` |
| E1.3 | Sandbox — netns, audit hook, rlimits, wall clock | done | `c71403f` |
| E2.1 | OHLC sources — read-only `/info`, CSV, cache | done | `01acdc5` |
| E2.2 | Event-driven engine, R-based and net of costs | done | `0727b41` |
| E2.3 | Persistence — strategies, versions, runs, provenance `engine` | done | `c1a7b4c` |
| E3 | Designer surface — Monaco, versions, backtest from the UI | done | `3341e4d` |
| E3.2 | Visual block designer, palette served from the schema | done | (this commit) |
| E4 | Parameter sweeps into the existing topography | done | `749959f` |
| E5 | Execution — dry-run and testnet, journal, stage scaling | done | `3341e4d` |

### Not done, deliberately

| Task | Why |
| --- | --- |
| Mainnet execution | Out of scope by instruction, and refused four ways. See PROGRESS.md, "The next step toward mainnet". |

## Next

1. **Exercise the testnet signature** against the live venue — the one part of
   E5 that could not be verified here. See PROGRESS.md, "Open / not verified".
2. **Browser-level testing** for the designer. The logic and the schema
   agreement are covered; the components are not.
3. **Async sweeps** with a job queue, when a grid larger than 400 cells is
   actually wanted.
4. **Cache coverage records**, so a range that legitimately holds no bars stops
   being re-fetched.
