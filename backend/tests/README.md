# Test suite

```bash
bash backend/scripts/dev_db.sh     # embedded Postgres on :55432
cd backend && python -m pytest
```

On a fresh clone that is **326 passed, 16 skipped**. Nothing fails.

## Why some tests skip

A handful of checks verify behaviour against data this repository deliberately
does not ship: a private research workbook and the result directories of the
upstream backtesting engines. Those tests locate their inputs through the
environment and **skip with an explicit reason when it is absent** — they never
fail for want of data, and they never carry an identifier from a private setup
in their source.

`pytest -rs` prints the reason for every skip.

| Variable | Used by | Effect when unset |
| --- | --- | --- |
| `HADRIAN3_REAL_XLSX` | import and reconciliation against a private workbook | falls back to the repository root, then to the shipped sample |
| `HADRIAN2_RESULTS_DIR` | upstream engine import and consistency checks | those tests skip |
| `HADRIAN_ENGINE_RESULTS_DIR` | as above | those tests skip |
| `HADRIAN3_ASSET_EXPECTATIONS` | asset derivation against real sources | those tests skip |
| `HADRIAN3_ENGINE_RECON` | engine reconciliation for one named system | that test skips |
| `HADRIAN_ENGINE_EXCLUDE` | *not a test variable* — see below | only the built-in exclusions apply |

## `HADRIAN3_ASSET_EXPECTATIONS`

Path to a JSON file **outside this repository** listing the asset each system
should resolve to. `null` means "no evidence in the source, so the importer's
default applies".

```json
{
  "xlsx": {
    "<system-with-ticker-in-timeframe-column>": "XMR",
    "<another-such-system>": "DOT",
    "<system-with-a-real-timeframe-there>": null
  },
  "engine": {
    "<engine-system-traded-on-avax>": "AVAX",
    "<engine-system-traded-on-eth>": "ETH"
  }
}
```

Every key must exist in the corresponding source, or the test fails — that is
the point: it catches a rename or a dropped system, not just a wrong asset.

## `HADRIAN3_ENGINE_RECON`

One system to reconcile against its engine `results.xlsx`, as
`<system>:<config-label>:<n>`:

```bash
export HADRIAN3_ENGINE_RECON="my_system:ATRSL_BestTP:195"
```

The test asserts that the persisted trade count matches `<n>` and that the
reported EV equals the EV read live from that config's row. Only the pointer is
supplied; every figure is read from the source at run time.

## `HADRIAN_ENGINE_EXCLUDE`

A runtime setting for the importer, not for tests: a comma-separated list of
result-directory names that are not systems. Engine test scaffolds
(`engine_test`, `minimal_test`) and anything ending in `_backup` are excluded
already.

```bash
export HADRIAN_ENGINE_EXCLUDE="scratch_run,old_variant"
```

## Running the full set

```bash
export HADRIAN3_REAL_XLSX=/path/to/workbook.xlsx
export HADRIAN2_RESULTS_DIR=/path/to/hadrian2/results
export HADRIAN_ENGINE_RESULTS_DIR=/path/to/engine/results
export HADRIAN3_ASSET_EXPECTATIONS=/path/to/expectations.json
export HADRIAN3_ENGINE_RECON="my_system:ATRSL_BestTP:195"
cd backend && python -m pytest          # 342 passed
```
