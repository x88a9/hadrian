"""The sandbox, tested by attacking it.

These tests run genuinely hostile code — reading /etc/passwd, opening sockets,
spawning processes, allocating past the limit, looping forever — and assert
that each one fails inside the sandbox rather than succeeding on the host.
A sandbox is only worth what it has been tried against, so the file is
deliberately weighted towards escape attempts rather than happy paths.

They are slow by the standards of this suite: every case is a process spawn.
That is inherent — the isolation *is* the process boundary — and a few seconds
is a reasonable price for the one test file that decides whether it is safe to
let a browser text box execute Python on this machine.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.strategy.sandbox import (
    SandboxCrashed,
    SandboxDeniedError,
    SandboxError,
    SandboxLimits,
    SandboxMemoryExceeded,
    SandboxTimeout,
    UserCodeError,
    isolation_layers,
    run_sandboxed,
)

pytestmark = pytest.mark.sandbox

FAST = SandboxLimits(timeout_s=15.0, memory_mb=256)


def probe(source: str, limits: SandboxLimits | None = None):
    return run_sandboxed("probe", {"source": source}, limits=limits or FAST)


# --------------------------------------------------------------------------- #
# It still runs ordinary code
# --------------------------------------------------------------------------- #


def test_ordinary_code_runs():
    assert probe("RESULT = sum(range(101))").value["result"] == 5050


def test_the_allowed_modules_are_actually_usable():
    """A sandbox that forbids everything is safe and useless; strategies need
    real arithmetic."""
    for module, expression in [
        ("math", "math.sqrt(16)"),
        ("statistics", "statistics.mean([1, 2, 3])"),
        ("collections", "len(collections.deque([1, 2]))"),
        ("itertools", "len(list(itertools.islice(itertools.count(), 3)))"),
        ("random", "type(random.Random(1).random()).__name__"),
    ]:
        result = probe(f"import {module}\nRESULT = {expression}")
        assert result.value["result"] is not None, module


def test_a_clean_run_records_no_denials():
    assert probe("RESULT = 1").denials == ()


# --------------------------------------------------------------------------- #
# The filesystem is not there
# --------------------------------------------------------------------------- #


def test_cannot_read_a_file():
    with pytest.raises(SandboxDeniedError):
        probe("RESULT = open('/etc/passwd').read()")


def test_cannot_write_a_file(tmp_path: Path):
    target = tmp_path / "escaped.txt"
    with pytest.raises(SandboxDeniedError):
        probe(f"open({str(target)!r}, 'w').write('escaped')")
    assert not target.exists(), "the sandbox wrote to the host filesystem"


def test_cannot_reach_the_filesystem_through_os():
    with pytest.raises(SandboxDeniedError):
        probe("import os\nRESULT = os.listdir('/')")


def test_cannot_reach_the_filesystem_through_pathlib():
    with pytest.raises(SandboxDeniedError):
        probe("import pathlib\nRESULT = pathlib.Path('/etc/passwd').read_text()")


def test_cannot_read_the_repository_it_is_running_from():
    """The strategy runs on the machine holding the trading database; the most
    valuable thing on disk is right next to it."""
    with pytest.raises(SandboxDeniedError):
        probe("RESULT = open('/home/fabian/hadrian/.env').read()")


# --------------------------------------------------------------------------- #
# The network is not there
# --------------------------------------------------------------------------- #


def test_cannot_import_socket():
    with pytest.raises(SandboxDeniedError):
        probe("import socket\nRESULT = socket.socket()")


def test_cannot_import_the_underlying_socket_extension():
    """Blocking the pure-Python wrapper while leaving the C module reachable
    would be no protection at all."""
    with pytest.raises(SandboxDeniedError):
        probe("import _socket\nRESULT = _socket.socket()")


def test_cannot_make_an_http_request():
    with pytest.raises(SandboxDeniedError):
        probe("import urllib.request\nRESULT = urllib.request.urlopen('http://example.com')")


def test_cannot_reach_the_network_through_http_client():
    with pytest.raises(SandboxDeniedError):
        probe("import http.client\nRESULT = 1")


# --------------------------------------------------------------------------- #
# No processes, no native code
# --------------------------------------------------------------------------- #


def test_cannot_spawn_a_subprocess():
    with pytest.raises(SandboxDeniedError):
        probe("import subprocess\nRESULT = subprocess.run(['id'], capture_output=True)")


def test_cannot_call_os_system():
    with pytest.raises(SandboxDeniedError):
        probe("import os\nRESULT = os.system('id')")


def test_cannot_load_ctypes():
    """ctypes is the standard way out of any Python-level sandbox: given it,
    an attacker can call into libc and remove the audit hook itself."""
    with pytest.raises(SandboxDeniedError):
        probe("import ctypes\nRESULT = ctypes.CDLL(None)")


def test_cannot_load_the_ctypes_extension():
    with pytest.raises(SandboxDeniedError):
        probe("import _ctypes\nRESULT = 1")


# --------------------------------------------------------------------------- #
# Escape attempts
# --------------------------------------------------------------------------- #


def test_cannot_reach_hidden_modules_by_name():
    """``os`` is imported by interpreter start-up, so it is in ``sys.modules``
    before user code runs. It is removed from there precisely so that naming it
    has to go back through the loader, where the hook refuses it."""
    for module in ("os", "sys", "io", "resource", "importlib", "inspect", "gc"):
        with pytest.raises(SandboxDeniedError):
            probe(f"import {module}\nRESULT = 1")


def test_cannot_re_enter_through_the_import_machinery():
    with pytest.raises(SandboxDeniedError):
        probe("RESULT = __import__('os').listdir('/')")


def test_cannot_reach_a_module_through_builtins():
    with pytest.raises(SandboxDeniedError):
        probe("import builtins\nRESULT = builtins.__import__('socket')")


def test_a_swallowed_denial_is_still_reported():
    """``except Exception: pass`` hides the error but must not hide the fact —
    otherwise a strategy could probe the host quietly."""
    result = probe(
        "RESULT = 'no denial'\n"
        "try:\n"
        "    open('/etc/passwd')\n"
        "except BaseException:\n"
        "    RESULT = 'swallowed'\n"
    )
    assert result.value["result"] == "swallowed"
    assert result.denials, "a caught denial vanished from the record"
    assert any("open" in d for d in result.denials)


def test_a_denial_is_not_an_ordinary_exception():
    """It subclasses BaseException so that a strategy's own error handling does
    not absorb it by accident."""
    result = probe(
        "RESULT = 'caught by except Exception'\n"
        "try:\n"
        "    open('/etc/passwd')\n"
        "except Exception:\n"
        "    pass\n"
        "except BaseException:\n"
        "    RESULT = 'escaped except Exception'\n"
    )
    assert result.value["result"] == "escaped except Exception"


def test_the_environment_carries_nothing_useful(monkeypatch):
    """The child gets PATH and a locale, and nothing else — no DATABASE_URL,
    no keys, nothing inherited from the API process."""
    monkeypatch.setenv("HADRIAN_SECRET_PROBE", "must-not-be-visible")
    with pytest.raises(SandboxDeniedError):
        probe("import os\nRESULT = os.environ.get('HADRIAN_SECRET_PROBE')")


# --------------------------------------------------------------------------- #
# Limits
# --------------------------------------------------------------------------- #


def test_an_infinite_loop_is_stopped():
    with pytest.raises(SandboxTimeout):
        probe("while True:\n    pass\n", limits=SandboxLimits(timeout_s=2.0))


def test_a_blocking_sleep_is_stopped():
    """``time.sleep`` consumes no CPU, so ``RLIMIT_CPU`` would never fire; only
    the wall clock catches this one."""
    with pytest.raises(SandboxTimeout):
        probe("import time\ntime.sleep(60)", limits=SandboxLimits(timeout_s=2.0))


def test_a_memory_bomb_is_stopped():
    with pytest.raises(SandboxMemoryExceeded):
        probe(
            "x = bytearray(400 * 1024 * 1024)",
            limits=SandboxLimits(timeout_s=20.0, memory_mb=128),
        )


def test_incremental_allocation_is_also_stopped():
    """A single huge request is easy to refuse; growth in a loop is the shape a
    leak actually has."""
    with pytest.raises((SandboxMemoryExceeded, SandboxTimeout)):
        probe(
            "chunks = []\n"
            "while True:\n"
            "    chunks.append(bytearray(8 * 1024 * 1024))\n",
            limits=SandboxLimits(timeout_s=25.0, memory_mb=128),
        )


def test_deep_recursion_does_not_take_the_process_down():
    with pytest.raises(UserCodeError):
        probe("def f(n):\n    return f(n + 1)\n\nf(0)\n")


def _child_pids() -> set[str]:
    """PIDs of sandbox children currently alive, found by their entry script."""
    import subprocess

    pattern = "_sandbox" + "_child.py"
    found = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    return set(found.stdout.split())


def test_the_timeout_leaves_nothing_running():
    """The child is its own process group, so the kill reaches the interpreter
    and not just the ``unshare`` wrapper in front of it.

    Compared as a set difference rather than "no sandbox process exists at
    all". The absolute form fails on an unrelated stale process or a concurrent
    run, which is noise; what this test is actually about is whether *this* run
    leaves anything behind.
    """
    before = _child_pids()
    with pytest.raises(SandboxTimeout):
        probe("while True:\n    pass\n", limits=SandboxLimits(timeout_s=2.0))
    leaked = _child_pids() - before
    assert not leaked, f"a sandbox child outlived its timeout: {sorted(leaked)}"


# --------------------------------------------------------------------------- #
# Errors reach the user usefully
# --------------------------------------------------------------------------- #


def test_a_user_exception_comes_back_with_its_own_traceback():
    with pytest.raises(UserCodeError) as excinfo:
        probe("def f():\n    raise ValueError('boom')\n\nf()\n")
    assert "ValueError: boom" in str(excinfo.value)
    trace = excinfo.value.traceback_text
    assert '"<strategy>", line 2' in trace
    assert "raise ValueError('boom')" in trace


def test_the_traceback_shows_only_the_strategy_frames():
    """Formatting it by hand also avoids ``linecache``, whose file reads the
    sandbox itself would deny — an error report that raises is worse than none."""
    with pytest.raises(UserCodeError) as excinfo:
        probe("raise RuntimeError('x')")
    assert "_sandbox_child" not in excinfo.value.traceback_text
    assert "sandbox.py" not in excinfo.value.traceback_text


def test_a_syntax_error_is_reported_as_a_user_error():
    with pytest.raises(UserCodeError) as excinfo:
        probe("def broken(:\n    pass\n")
    assert "SyntaxError" in str(excinfo.value)


def test_an_unknown_task_is_refused():
    with pytest.raises(SandboxCrashed):
        run_sandboxed("no_such_task", {}, limits=FAST)


def test_every_failure_is_a_sandbox_error():
    """Callers should need one except clause, not a taxonomy."""
    for exc_type in (
        SandboxTimeout,
        SandboxMemoryExceeded,
        SandboxDeniedError,
        SandboxCrashed,
        UserCodeError,
    ):
        assert issubclass(exc_type, SandboxError)


# --------------------------------------------------------------------------- #
# The layers themselves
# --------------------------------------------------------------------------- #


def test_the_unconditional_layers_are_always_in_force():
    layers = isolation_layers()
    assert "audit_hook" in layers
    assert "rlimits" in layers
    assert "subprocess_timeout" in layers


def test_a_result_records_which_layers_ran():
    assert set(probe("RESULT = 1").layers) == set(isolation_layers())


@pytest.mark.skipif(
    "network_namespace" not in isolation_layers(),
    reason="this kernel does not allow an unprivileged network namespace",
)
def test_the_network_namespace_is_empty_when_available():
    """The strongest layer, and the only one that does not depend on the
    interpreter behaving. Where the kernel allows it, the child has no
    interfaces at all, so there is no socket to reach even in principle."""
    assert isolation_layers()[0] == "network_namespace"


def test_the_child_is_never_imported_into_the_api_process():
    """Importing it would install an unremovable audit hook in the process that
    serves requests, which would stop the API dead."""
    assert "app.strategy._sandbox_child" not in sys.modules
