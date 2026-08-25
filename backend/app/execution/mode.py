"""The execution-mode gate — the one place that decides whether an order may
leave this process, and where it may go.

This module is the whole of the safety boundary for the engine phase. It is
deliberately small, dependency-free and readable in one sitting, because its
correctness is not something to be inferred from behaviour.

The boundary
------------
``MAINNET`` exists as an enum member because the type should be honest about
the eventual target, and because a mode the code cannot name is a mode the code
cannot refuse by name. It is refused four ways, and each one alone would be
enough:

1. ``parse_execution_mode`` — the only conversion from configuration or request
   data into an ``ExecutionMode`` — will not return ``MAINNET``. There is no
   setting, environment variable or payload that resolves to it. The one escape
   hatch, ``allow_mainnet=True``, is passed by nothing in the tree and is
   checked by ``tests/test_execution_boundary.py``.
2. ``require_permitted`` raises ``MainnetDisabled`` on every path that could
   place an order.
3. ``EXCHANGE_BASE_URLS`` has no mainnet entry, and no mainnet exchange host
   appears anywhere in the repository. Removing the guards would not produce a
   working mainnet order; it would produce a ``KeyError``.
4. No signing credential is committed, defaulted or generated. ``TESTNET``
   signing keys come from the operator's environment and nowhere else.

Arming mainnet is a separate, manual, human-reviewed change. It is not
something this phase can do by accident, and not something a future refactor
can do quietly — the source-level test fails loudly first.

Market data is not execution
----------------------------
Reading candles from the public ``/info`` endpoint is not trading, and mainnet
price history is the only history worth backtesting against. ``InfoClient``
therefore reads mainnet freely; it holds no key material and cannot sign. The
split between reading prices and sending orders is the reason this boundary can
be strict without being useless.
"""

from __future__ import annotations

import enum

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


class ExecutionMode(str, enum.Enum):
    """Where a generated order is allowed to go."""

    #: Orders are computed and journalled, and no socket is opened. The default
    #: everywhere, including when configuration is missing or unreadable.
    DRY_RUN = "dry_run"

    #: Real orders against the Hyperliquid testnet, signed with a testnet-only
    #: agent wallet supplied through the environment.
    TESTNET = "testnet"

    #: Real money. Refused throughout this phase — see the module docstring.
    MAINNET = "mainnet"


#: Modes an order may actually be executed in.
PERMITTED_MODES: frozenset[ExecutionMode] = frozenset(
    {ExecutionMode.DRY_RUN, ExecutionMode.TESTNET}
)

#: What you get when nothing says otherwise. Failing safe means failing to
#: ``DRY_RUN``, never to a mode that opens a socket.
DEFAULT_EXECUTION_MODE: ExecutionMode = ExecutionMode.DRY_RUN

#: Exchange endpoints per mode. ``DRY_RUN`` has none because it never connects;
#: ``MAINNET`` has none because this phase does not ship the address.
EXCHANGE_BASE_URLS: dict[ExecutionMode, str] = {
    ExecutionMode.TESTNET: "https://api.hyperliquid-testnet.xyz",
}


class MainnetDisabled(RuntimeError):
    """Raised when a code path asks for mainnet execution.

    Not a failure to be retried or caught-and-continued. It means a caller
    reached for real money on a build that does not ship it.
    """


class UnknownExecutionMode(ValueError):
    """The configured or requested execution mode is not a known mode."""


def parse_execution_mode(
    raw: str | ExecutionMode | None,
    *,
    allow_mainnet: bool = False,
) -> ExecutionMode:
    """Resolve configuration or request data into an ``ExecutionMode``.

    ``None`` and the empty string resolve to :data:`DEFAULT_EXECUTION_MODE`, so
    a missing setting is safe rather than fatal. Anything unrecognised raises,
    because silently downgrading a mode the operator asked for would be its own
    kind of surprise.

    ``"mainnet"`` raises :class:`MainnetDisabled` unless ``allow_mainnet`` is
    set. Nothing in this repository sets it; it exists so that the eventual,
    deliberate arming change is a one-line diff at a single call site rather
    than a rewrite of this module, and so that the source-level test has a
    single token to watch.
    """
    if raw is None:
        return DEFAULT_EXECUTION_MODE

    if isinstance(raw, ExecutionMode):
        mode = raw
    else:
        text = str(raw).strip().lower()
        if not text:
            return DEFAULT_EXECUTION_MODE
        try:
            mode = ExecutionMode(text)
        except ValueError:
            known = ", ".join(m.value for m in ExecutionMode)
            raise UnknownExecutionMode(
                f"unknown execution mode {raw!r}; known modes are {known}"
            ) from None

    if mode is ExecutionMode.MAINNET and not allow_mainnet:
        raise MainnetDisabled(
            "mainnet execution is not available in this build. Arming it is a "
            "separate, manually reviewed change — see the module docstring of "
            "app/execution/mode.py."
        )
    return mode


def require_permitted(mode: ExecutionMode) -> ExecutionMode:
    """Gate for every path that can place an order. Returns ``mode`` unchanged
    when it is permitted, so it reads naturally at the top of a call::

        mode = require_permitted(self.mode)

    Raises :class:`MainnetDisabled` for mainnet and
    :class:`UnknownExecutionMode` for anything that is not an
    :class:`ExecutionMode` at all — a caller passing a bare string here has
    bypassed :func:`parse_execution_mode`, which is itself the bug.
    """
    if not isinstance(mode, ExecutionMode):
        raise UnknownExecutionMode(
            f"expected an ExecutionMode, got {type(mode).__name__}: {mode!r}. "
            "Resolve configuration through parse_execution_mode()."
        )
    if mode not in PERMITTED_MODES:
        raise MainnetDisabled(
            f"execution mode {mode.value!r} is refused in this build. Permitted "
            f"modes are {', '.join(sorted(m.value for m in PERMITTED_MODES))}."
        )
    return mode


def exchange_base_url(mode: ExecutionMode) -> str:
    """Base URL of the exchange for ``mode``.

    Gated, so this cannot be used to sidestep :func:`require_permitted`.
    ``DRY_RUN`` raises rather than returning a placeholder: a dry run that is
    resolving an exchange URL has already lost track of what it is.
    """
    require_permitted(mode)
    try:
        return EXCHANGE_BASE_URLS[mode]
    except KeyError:
        raise MainnetDisabled(
            f"no exchange endpoint is configured for mode {mode.value!r}; "
            "DRY_RUN must not connect to an exchange."
        ) from None
