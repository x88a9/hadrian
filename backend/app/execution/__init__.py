"""Order-execution layer.

Nothing in this package may place an order without passing through
``app.execution.mode``. See docs/DECISIONS.md, "The execution boundary".
"""

from app.execution.mode import (
    DEFAULT_EXECUTION_MODE,
    EXCHANGE_BASE_URLS,
    PERMITTED_MODES,
    ExecutionMode,
    MainnetDisabled,
    UnknownExecutionMode,
    exchange_base_url,
    parse_execution_mode,
    require_permitted,
)

__all__ = [
    "DEFAULT_EXECUTION_MODE",
    "EXCHANGE_BASE_URLS",
    "PERMITTED_MODES",
    "ExecutionMode",
    "MainnetDisabled",
    "UnknownExecutionMode",
    "exchange_base_url",
    "parse_execution_mode",
    "require_permitted",
]
