# Progress

Running record of what is built, verified and open. Newest phase first.

---

## Wiederherstellungspunkte / Restore points

| Tag | Commit | Date | What it restores |
| --- | --- | --- | --- |
| `pre-engine-phase` | `b85eea864d111a5174e446c82df944faf96a46b9` | 2026-08-25 | State immediately before the engine phase (E1–E5): 75 imported systems, quant analytics, verified risk calculator, live-trading journal. Annotated tag, pushed to origin. |

Roll back with:

```bash
git reset --hard pre-engine-phase     # discards local work
git checkout -b rescue pre-engine-phase   # keeps main, branches from the point
```

---

## Baseline measured at the restore point

Measured on 2026-08-25 against `b85eea8`, not taken from prior notes:

- Backend suite: **326 passed, 16 skipped** (342 collected) with the dev Postgres
  up (`bash backend/scripts/dev_db.sh`). Without it, 163 pass and 179 skip —
  the integration tests skip cleanly rather than fail.
- The 16 remaining skips are unrelated to the database (see `pytest -rs`).
- Frontend has no test runner; `tsc` and `next build` are the gate there.

> Note for the record: the engine-phase brief cited 482 tests. The repository at
> the restore point collects 342. The suite is green; the number in the brief
> does not correspond to anything measurable here. Growth is tracked from **342**.

---

## Engine phase (E1–E5) — in progress

Started 2026-08-25 from `pre-engine-phase`.

Status: planning.
