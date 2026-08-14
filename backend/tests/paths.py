"""Data locations used by the test suite.

Tests must pass on a fresh clone that has no private data. They must also stay
useful on a machine that *does* have it. Both are resolved here rather than
hard-coding anyone's home directory:

* :data:`SAMPLE_XLSX` — the synthetic workbook in ``samples/``. Always present,
  so every test built on it runs everywhere.
* :data:`REAL_XLSX` — the private research workbook. Located via
  ``HADRIAN3_REAL_XLSX`` or, failing that, the repository root. Tests that
  assert real-data specifics skip when it is absent.
* :data:`HADRIAN2_DIR` / :data:`ENGINE_DIR` — result directories of the upstream
  research engines, via environment or ``Settings``. Empty means unavailable.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SAMPLE_XLSX = REPO_ROOT / "samples" / "backtesting_repository_sample.xlsx"

REAL_XLSX = Path(
    os.environ.get("HADRIAN3_REAL_XLSX")
    or REPO_ROOT / "Backtesting Repository.xlsx"
)

HADRIAN2_DIR = os.environ.get("HADRIAN2_RESULTS_DIR", "")
ENGINE_DIR = os.environ.get("HADRIAN_ENGINE_RESULTS_DIR", "")


def has_real_xlsx() -> bool:
    return REAL_XLSX.is_file()


def has_engine_sources() -> bool:
    return bool(HADRIAN2_DIR) and bool(ENGINE_DIR) and (
        Path(HADRIAN2_DIR).is_dir() and Path(ENGINE_DIR).is_dir()
    )
