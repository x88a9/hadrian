from datetime import date
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root, resolved from this file so defaults stay machine-independent.
REPO_ROOT = Path(__file__).resolve().parents[3]

# Shipped stand-in for the private research workbook. See samples/README.md.
SAMPLE_XLSX = REPO_ROOT / "samples" / "backtesting_repository_sample.xlsx"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://hadrian3:hadrian3@localhost:5432/hadrian3"

    # Defaults to the synthetic sample workbook so a fresh clone works without
    # any private data. Point XLSX_PATH at your own workbook to import it.
    XLSX_PATH: str = str(SAMPLE_XLSX)
    IS_OOS_SPLIT_DATE: date = date(2024, 1, 1)

    # Optional result directories of the upstream research engines. Empty means
    # "not available"; the programmatic importer then reports nothing to import.
    HADRIAN2_RESULTS_DIR: str = ""
    HADRIAN_ENGINE_RESULTS_DIR: str = ""


settings = Settings()
