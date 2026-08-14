# Sample data

`backtesting_repository_sample.xlsx` is a **synthetic** stand-in for the private
research workbook this platform was built around. Nothing in it describes a real
trading result — system names, rules, prices and trades are generated from a
fixed seed by `backend/scripts/generate_sample_workbook.py`.

It exists so that a fresh clone can import data, populate the dashboard and run
the full test suite without any private material.

## What it covers

The importer has to survive a workbook that grew organically over years, so the
sample reproduces the awkward parts rather than an idealised layout:

| Tab | Layout | Purpose |
| --- | --- | --- |
| `B-H1-901` | variant A | 140 trades, the only system still positive out-of-sample |
| `TREND-D1-902` | variant A | 190 trades spanning IS and OOS |
| `MR-M15-903` | variant A | 240 trades, high hit rate but a thin edge |
| `REV-H4-904` | variant A | 120 trades, low frequency |
| `BB-M5-905.v2` | variant B | older layout: name in `B3`, shifted trade columns |
| `VP-H1-906.wip` | variant A | unfinished backtest — metric block is all `#DIV/0!` |

Identifiers use a 9xx block and generic textbook rules, so nothing here collides
with or paraphrases a real research system.

Variant A puts the system name in `B2` and its metric values in row 9; variant B
uses `B3` and row 8 and labels the date column `Date` instead of `Date & Time`.
The parser is driven by header text rather than fixed coordinates precisely
because both exist in the wild.

Two properties of the generated data are deliberate.

**The results are a mixed bag** — one system grades D, the rest F. A sample where
everything was profitable would be a poor demonstration of a tool whose job is to
tell those cases apart.

**Every system performs worse out-of-sample than in-sample**, which is what real
systems do once the parameters stop being fitted to the data being measured:

| System | IS EV | OOS EV | IS win rate | OOS win rate |
| --- | ---: | ---: | ---: | ---: |
| `B-H1-901` | +0.57 | +0.23 | 32.1% | 25.0% |
| `TREND-D1-902` | +0.20 | −0.02 | 38.3% | 31.2% |
| `MR-M15-903` | +0.08 | −0.08 | 59.2% | 50.7% |
| `REV-H4-904` | +0.50 | −0.08 | 42.5% | 26.2% |
| `BB-M5-905.v2` | +0.62 | +0.15 | 56.7% | 39.7% |

A sample without that decay would make the IS/OOS split look like a formality.

## Regenerating

```bash
python backend/scripts/generate_sample_workbook.py
```

The seed is fixed, so the output is byte-stable. Adjust `SPECS` in that script
to change the systems it produces.

## Using your own workbook

Point `XLSX_PATH` at it (see `.env.example`), or mount it into the backend
container via `docker-compose.override.yml`. Tests that assert figures specific
to a private workbook look for it via `HADRIAN3_REAL_XLSX` and skip when it is
absent.
