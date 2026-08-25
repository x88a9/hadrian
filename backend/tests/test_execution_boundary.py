"""The execution boundary, checked against the source tree.

These tests deliberately read files instead of calling functions. A behavioural
test proves that today's code refuses mainnet; a source-level test proves that
tomorrow's code cannot start permitting it without someone noticing. The thing
being protected here is not a behaviour, it is an invariant of the repository.

If one of these fails, the correct response is almost never to relax the test.
Arming mainnet is a deliberate, human-reviewed change, and these assertions are
the record of that decision — see docs/DECISIONS.md, "The execution boundary".
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

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

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
APP_DIR = BACKEND_DIR / "app"
EXECUTION_DIR = APP_DIR / "execution"

#: The gate module and this test are allowed to name mainnet; they are what
#: refuses it. Everything else in the tree must not mention it at all.
MAINNET_NAMING_ALLOWED = {
    EXECUTION_DIR / "mode.py",
    Path(__file__).resolve(),
}


def app_sources() -> list[Path]:
    """Every Python module of the application, tests excluded."""
    return sorted(p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts)


# --------------------------------------------------------------------------- #
# Runtime behaviour of the gate
# --------------------------------------------------------------------------- #


def test_default_mode_is_dry_run():
    assert DEFAULT_EXECUTION_MODE is ExecutionMode.DRY_RUN


def test_missing_configuration_falls_back_to_dry_run():
    """Absent or blank configuration must fail *safe*, not fail closed-to-live."""
    for blank in (None, "", "   "):
        assert parse_execution_mode(blank) is ExecutionMode.DRY_RUN


def test_mainnet_is_not_a_permitted_mode():
    assert ExecutionMode.MAINNET not in PERMITTED_MODES
    assert PERMITTED_MODES == {ExecutionMode.DRY_RUN, ExecutionMode.TESTNET}


def test_parse_refuses_the_mainnet_string():
    with pytest.raises(MainnetDisabled):
        parse_execution_mode("mainnet")
    with pytest.raises(MainnetDisabled):
        parse_execution_mode("  MainNet  ")


def test_require_permitted_refuses_mainnet():
    with pytest.raises(MainnetDisabled):
        require_permitted(ExecutionMode.MAINNET)


def test_require_permitted_refuses_a_bare_string():
    """A caller holding a string skipped the parser, which is itself the bug."""
    with pytest.raises(UnknownExecutionMode):
        require_permitted("testnet")  # type: ignore[arg-type]


def test_require_permitted_passes_the_permitted_modes_through():
    for mode in (ExecutionMode.DRY_RUN, ExecutionMode.TESTNET):
        assert require_permitted(mode) is mode


def test_unknown_mode_raises_rather_than_downgrading():
    with pytest.raises(UnknownExecutionMode):
        parse_execution_mode("prod")


def test_no_mainnet_exchange_endpoint_exists():
    """Even without the guards there would be nothing to send an order to."""
    assert ExecutionMode.MAINNET not in EXCHANGE_BASE_URLS
    assert set(EXCHANGE_BASE_URLS) == {ExecutionMode.TESTNET}
    assert "testnet" in EXCHANGE_BASE_URLS[ExecutionMode.TESTNET]


def test_dry_run_has_no_exchange_endpoint():
    """A dry run resolving an exchange URL has lost track of what it is."""
    with pytest.raises(MainnetDisabled):
        exchange_base_url(ExecutionMode.DRY_RUN)


def test_exchange_base_url_gates_before_it_resolves():
    with pytest.raises(MainnetDisabled):
        exchange_base_url(ExecutionMode.MAINNET)


# --------------------------------------------------------------------------- #
# Source-level invariants
# --------------------------------------------------------------------------- #


def test_no_application_module_names_mainnet():
    """No automatic path — backtest, designer preview, scheduler, API — can
    reach mainnet, because no module outside the gate can even name it."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in app_sources()
        if path.resolve() not in MAINNET_NAMING_ALLOWED
        and re.search(r"ExecutionMode\.MAINNET|\bMAINNET\b", path.read_text())
    ]
    assert not offenders, (
        "these modules name mainnet execution; only the gate may: " f"{offenders}"
    )


def _arms_mainnet(tree: ast.AST) -> bool:
    """True if the module actually passes or assigns ``allow_mainnet=True``.

    Matched on the syntax tree rather than the text, so that prose explaining
    the token — as the gate's own docstring does — is not mistaken for a use
    of it.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "allow_mainnet" and (
                    not isinstance(kw.value, ast.Constant) or kw.value.value
                ):
                    return True
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            named = any(
                isinstance(t, ast.Name) and t.id == "allow_mainnet" for t in targets
            )
            if named and getattr(node.value, "value", None) is True:
                return True
    return False


def test_nothing_passes_allow_mainnet():
    """``allow_mainnet=True`` is the single deliberate arming token. Nothing in
    the repository passes it — that is the point of it having a name."""
    searched = app_sources() + sorted(
        p for p in (BACKEND_DIR / "tests").rglob("*.py") if "__pycache__" not in p.parts
    )
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in searched
        if path.resolve() != Path(__file__).resolve()
        and _arms_mainnet(ast.parse(path.read_text(), filename=str(path)))
    ]
    assert not offenders, f"these files arm mainnet: {offenders}"


def test_the_arming_check_would_catch_a_real_call():
    """Guard the guard: a text-matching version of the check above was fooled by
    the gate's own docstring, so verify it sees a genuine call and ignores prose."""
    assert _arms_mainnet(ast.parse("parse_execution_mode(x, allow_mainnet=True)"))
    assert _arms_mainnet(ast.parse("allow_mainnet = True"))
    assert _arms_mainnet(ast.parse("f(allow_mainnet=SOME_FLAG)"))
    assert not _arms_mainnet(ast.parse('"""pass allow_mainnet=True to arm."""'))
    assert not _arms_mainnet(ast.parse("f(allow_mainnet=False)"))


def test_the_only_allow_mainnet_definition_defaults_to_false():
    source = (EXECUTION_DIR / "mode.py").read_text()
    assert "allow_mainnet: bool = False" in source
    assert not re.search(r"allow_mainnet\s*:\s*bool\s*=\s*True", source)


def test_no_signing_library_is_importable_from_application_code():
    """Nothing outside the execution package may sign a transaction, and today
    nothing at all imports a signing library — testnet signing lands in
    ``app/execution/`` and is checked separately when it does."""
    signing = {"eth_account", "eth_keys", "web3", "coincurve", "secp256k1", "ecdsa"}
    offenders: list[str] = []
    for path in app_sources():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] in signing and EXECUTION_DIR not in path.parents:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: {name}")
    assert not offenders, f"signing libraries imported outside the gate: {offenders}"


def test_no_committed_credential_in_the_example_environment():
    """Every key-shaped variable in .env.example must be present but empty."""
    text = (REPO_ROOT / ".env.example").read_text()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        if re.search(r"KEY|SECRET|PRIVATE|MNEMONIC|SEED", name, re.IGNORECASE):
            assert value.strip() == "", (
                f"{name} carries a value in .env.example; a committed key is a "
                "leaked key"
            )


def test_example_environment_does_not_offer_mainnet():
    text = (REPO_ROOT / ".env.example").read_text()
    match = re.search(r"^EXECUTION_MODE=(.*)$", text, re.MULTILINE)
    assert match, "EXECUTION_MODE is not documented in .env.example"
    assert match.group(1).strip() == "dry_run"


def test_configuration_refuses_a_mainnet_environment(monkeypatch):
    """An operator setting EXECUTION_MODE=mainnet gets a refusal, not a build
    that quietly trades."""
    from app.core.config import Settings

    monkeypatch.setenv("EXECUTION_MODE", "mainnet")
    with pytest.raises(MainnetDisabled):
        Settings(_env_file=None)


def test_configured_default_is_dry_run(monkeypatch):
    from app.core.config import Settings

    monkeypatch.delenv("EXECUTION_MODE", raising=False)
    assert Settings(_env_file=None).EXECUTION_MODE is ExecutionMode.DRY_RUN
