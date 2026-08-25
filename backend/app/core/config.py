from datetime import date
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.execution.mode import ExecutionMode, parse_execution_mode

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

    # --- Engine phase --- #

    # Where generated orders may go. "dry_run" (default) opens no socket;
    # "testnet" trades against Hyperliquid testnet. "mainnet" is refused here
    # and everywhere else in this build — see app/execution/mode.py.
    EXECUTION_MODE: ExecutionMode = ExecutionMode.DRY_RUN

    # Read-only market-data endpoint. This is the public /info route: it serves
    # candles and metadata, takes no signature, and is not an order path.
    HL_INFO_URL: str = "https://api.hyperliquid.xyz/info"

    # Downloaded candles are cached here so a backtest is reproducible without
    # the network, and so a re-run does not re-fetch.
    CANDLE_CACHE_DIR: str = str(REPO_ROOT / "backend" / ".cache" / "candles")

    # Limits applied to untrusted user strategy code. Wall clock in seconds,
    # address space in MiB.
    SANDBOX_TIMEOUT_S: float = 10.0
    SANDBOX_MEMORY_MB: int = 512

    @field_validator("EXECUTION_MODE", mode="before")
    @classmethod
    def _validate_execution_mode(cls, v: object) -> ExecutionMode:
        """Configuration cannot select mainnet.

        ``parse_execution_mode`` raises ``MainnetDisabled`` for it, so an
        operator who sets ``EXECUTION_MODE=mainnet`` gets a refusal at import
        time with an explanation, rather than a build that quietly trades.
        """
        return parse_execution_mode(v)


settings = Settings()
