"""Running untrusted strategy code without letting it out.

User Python is not trusted. It is written in a browser text box by whoever can
reach the app, and it runs on the machine that holds the trading database and
the exchange credentials. Treating it as hostile is not paranoia about the
operator; it is what makes the feature safe to expose at all.

Four layers, weakest last
-------------------------
**A network namespace.** Where the kernel allows an unprivileged
``unshare --user --net``, the child runs with no network interfaces at all.
Nothing in the process — Python, a C extension, a syscall made through some
future hole — can reach a socket that does not exist. This is the only layer
that does not depend on the interpreter behaving.

**An audit hook.** ``sys.addaudithook`` fires from CPython's C level, cannot be
removed once installed, and sees file opens, socket creation, subprocess spawns
and imports before they happen. The child refuses all of them. Because the hook
denies ``open``, and imports need to open files, the set of modules importable
by user code is exactly the set imported before the hook went up — an allowlist
that costs nothing to maintain.

**Resource limits.** Address space, CPU seconds, file size zero, and a small
descriptor cap. A runaway allocation becomes a ``MemoryError`` rather than a
machine that starts swapping.

**A separate process with a wall clock.** The parent kills the whole process
group on timeout, so a strategy that blocks in C — where neither the audit hook
nor ``RLIMIT_CPU`` would fire promptly — still ends.

What this does not claim
------------------------
This is a sandbox against Python-level escape: filesystem, network,
subprocesses, imports, runaway loops and runaway memory. It is not a defence
against a CPython interpreter vulnerability or arbitrary native code, and no
in-process hook could be. Hostile multi-tenant code belongs in a container or a
VM. For a single-operator tool the layers here are the right trade, and saying
so plainly is better than implying more than they give.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "SandboxCrashed",
    "SandboxDeniedError",
    "SandboxError",
    "SandboxLimits",
    "SandboxMemoryExceeded",
    "SandboxResult",
    "SandboxTimeout",
    "UserCodeError",
    "isolation_layers",
    "run_sandboxed",
]

BACKEND_DIR = Path(__file__).resolve().parents[2]
CHILD_MODULE = Path(__file__).resolve().parent / "_sandbox_child.py"


class SandboxError(Exception):
    """Base for everything that can go wrong running untrusted code."""


class SandboxTimeout(SandboxError):
    """The strategy ran too long and was killed."""


class SandboxMemoryExceeded(SandboxError):
    """The strategy allocated past its address-space limit."""


class SandboxDeniedError(SandboxError):
    """The strategy attempted something policy forbids: a file, a socket, a
    subprocess, or an import outside the allowlist."""


class SandboxCrashed(SandboxError):
    """The child died without producing a parseable answer."""


class UserCodeError(SandboxError):
    """The strategy raised. Carries the user-facing traceback."""

    def __init__(self, message: str, traceback_text: str = ""):
        super().__init__(message)
        self.traceback_text = traceback_text


@dataclass(frozen=True)
class SandboxLimits:
    """What the child is allowed to consume.

    ``cpu_seconds`` is the ``RLIMIT_CPU`` backstop and sits above
    ``timeout_s`` on purpose: the wall clock should be what normally stops a
    slow strategy, because it produces a clean, explainable kill, while the CPU
    limit exists for the case where the wall clock cannot be enforced in time.
    """

    timeout_s: float = 10.0
    memory_mb: int = 256
    cpu_seconds: int = 0  # 0 → derived from timeout_s

    def resolved_cpu_seconds(self) -> int:
        return self.cpu_seconds or max(1, int(self.timeout_s) + 5)


@dataclass(frozen=True)
class SandboxResult:
    value: Any
    #: Policy violations recorded during the run, including ones the strategy
    #: caught and swallowed. Empty on a clean run.
    denials: tuple[str, ...] = ()
    #: Which isolation layers were actually in force, for the record.
    layers: tuple[str, ...] = ()
    stderr: str = ""


@lru_cache(maxsize=1)
def _network_namespace_command() -> tuple[str, ...]:
    """``unshare`` prefix that puts the child in an empty network namespace, or
    an empty tuple where the kernel will not allow it unprivileged.

    Probed once by actually trying it, because the answer depends on kernel
    configuration (``kernel.unprivileged_userns_clone``, seccomp policy,
    container settings) and not on anything that can be read off reliably.
    """
    unshare = shutil.which("unshare")
    if not unshare:
        return ()
    try:
        probe = subprocess.run(
            [unshare, "--user", "--map-root-user", "--net", "--", "true"],
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    if probe.returncode != 0:
        return ()
    return (unshare, "--user", "--map-root-user", "--net", "--")


def isolation_layers() -> tuple[str, ...]:
    """The layers in force on this machine, strongest first.

    Exposed so the UI can be honest about it, and so a test can assert that the
    layers that are supposed to be unconditional really are.
    """
    layers = ["audit_hook", "rlimits", "subprocess_timeout"]
    if _network_namespace_command():
        layers.insert(0, "network_namespace")
    return tuple(layers)


def run_sandboxed(
    task: str,
    payload: dict[str, Any],
    *,
    limits: SandboxLimits | None = None,
) -> SandboxResult:
    """Run one task in the sandbox and return its result.

    Raises a :class:`SandboxError` subclass for every failure mode, so a caller
    never has to inspect a return value to find out whether the run was real.
    """
    limits = limits or SandboxLimits()

    request = json.dumps(
        {
            "task": task,
            "payload": payload,
            "limits": {
                "memory_mb": limits.memory_mb,
                "cpu_seconds": limits.resolved_cpu_seconds(),
            },
        }
    )

    command = [
        *_network_namespace_command(),
        sys.executable,
        # -I: isolated. PYTHONPATH, PYTHONSTARTUP and the user site directory
        # are ignored, so nothing in the environment can add an import root.
        # The child gets its one path from argv instead.
        "-I",
        str(CHILD_MODULE),
        str(BACKEND_DIR),
    ]

    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        # Its own process group, so a timeout kills the whole tree rather than
        # just the unshare wrapper and leaving the interpreter orphaned.
        start_new_session=True,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"},
    )

    try:
        stdout, stderr = proc.communicate(request, timeout=limits.timeout_s)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        proc.communicate()
        raise SandboxTimeout(
            f"strategy exceeded the {limits.timeout_s:g}s time limit and was stopped"
        ) from None

    if not stdout.strip():
        raise _crash_reason(proc.returncode, stderr, limits)

    try:
        response = json.loads(stdout)
    except ValueError:
        raise SandboxCrashed(
            f"sandbox produced unreadable output (exit {proc.returncode}): "
            f"{stdout[:400]}"
        ) from None

    denials = tuple(response.get("denials", ()))
    layers = isolation_layers()

    if response.get("ok"):
        return SandboxResult(
            value=response.get("value"),
            denials=denials,
            layers=layers,
            stderr=stderr,
        )

    kind = response.get("error", "")
    message = response.get("message", "the strategy failed")
    if kind == "denied":
        raise SandboxDeniedError(message)
    if kind == "memory":
        raise SandboxMemoryExceeded(message)
    if kind == "user_error":
        raise UserCodeError(message, response.get("traceback", ""))
    raise SandboxCrashed(f"{kind or 'unknown error'}: {message}")


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


def _crash_reason(returncode: int | None, stderr: str, limits: SandboxLimits) -> SandboxError:
    """Turn a silent death into the most specific explanation available.

    A child that produced no output cannot say why it stopped, so the signal is
    the only evidence there is — and the two that matter here are the ones the
    limits produce.
    """
    if returncode == -signal.SIGXCPU:
        return SandboxTimeout(
            f"strategy exhausted its {limits.resolved_cpu_seconds()}s CPU budget"
        )
    if returncode == -signal.SIGKILL:
        return SandboxTimeout("strategy was killed before it produced a result")
    if "MemoryError" in stderr or "Cannot allocate memory" in stderr:
        return SandboxMemoryExceeded(
            f"strategy exceeded the {limits.memory_mb} MiB memory limit"
        )
    return SandboxCrashed(
        f"sandbox exited with code {returncode} and no result. stderr: "
        f"{stderr.strip()[:400] or '(empty)'}"
    )
