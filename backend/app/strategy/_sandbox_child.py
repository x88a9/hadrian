"""The inside of the sandbox. Runs as a separate, isolated interpreter.

Never import this from application code — it is a process entry point, spawned
by ``app.strategy.sandbox`` and speaking JSON over stdin/stdout. Importing it
in-process would install an audit hook that cannot be removed again, in the
process that serves the API.

Order of operations matters here and is the whole design:

1. Put the backend on ``sys.path`` and import everything the task will need,
   while imports are still allowed. What is not imported by the end of this
   step can never be imported.
2. Read the payload from stdin, while the descriptor is still readable.
3. Apply resource limits.
4. Install the audit hook. From this line on the interpreter cannot open a
   file, create a socket, spawn a process, load ``ctypes`` or import anything
   new — and the hook itself cannot be uninstalled, because CPython provides
   no way to remove one.
5. Only then execute the user's code.

Denials are both raised and recorded. Raising stops the operation; recording
means an attempt that user code catches and swallows still shows up in the
result, so ``except Exception: pass`` hides the error but not the fact.
"""

from __future__ import annotations

import json
import sys

# -- step 1: imports, while they are still permitted ------------------------ #
#
# argv[1] is the backend directory. The child runs under ``-I``, so PYTHONPATH
# is ignored and this is the only way in — which is the point: nothing the
# environment says can add an import root.

if len(sys.argv) > 1:
    sys.path.insert(0, sys.argv[1])

import dataclasses  # noqa: E402
import datetime  # noqa: E402
import math  # noqa: E402
import random  # noqa: E402
import resource  # noqa: E402
import statistics  # noqa: E402

#: Held directly, so that hiding these from ``sys.modules`` later does not
#: cost this module the ability to read its input or write its answer.
_SYS = sys
_STDOUT = sys.stdout

from app.strategy.interface import (  # noqa: E402
    Bar,
    Context,
    LookaheadError,
    PositionView,
    Signal,
    Strategy,
    StrategyError,
)

#: Modules user code may reach. Anything not already imported by the time the
#: hook goes up cannot be imported at all, so this list is the whole of it.
#: Deliberately small and deliberately without ``os``, ``sys``, ``pathlib``,
#: ``socket``, ``subprocess``, ``importlib``, ``ctypes`` or ``pickle``.
ALLOWED_MODULES = frozenset(
    {
        "math",
        "statistics",
        "random",
        "datetime",
        "dataclasses",
        "json",
        "collections",
        "itertools",
        "functools",
        "typing",
        "enum",
        "abc",
        "numbers",
        "decimal",
        "fractions",
        "bisect",
        "heapq",
        "copy",
        "re",
        "app",
        "__future__",
    }
)

#: Audit events refused outright. Prefixes, matched against the event name.
#: ``open`` covers every file access CPython performs, including the ones an
#: import would need, which is why the allowlist above works by pre-import.
BLOCKED_EVENTS = (
    "open",
    "socket.",
    "os.",
    "subprocess.",
    "shutil.",
    "ctypes.",
    "cpython.",
    "urllib.",
    "ftplib.",
    "smtplib.",
    "imaplib.",
    "poplib.",
    "http.client",
    "webbrowser.",
    "pty.",
    "fcntl.",
    "mmap.",
    "resource.setrlimit",
    "pickle.",
    "marshal.",
    "glob.",
    "tempfile.",
    "sqlite3.",
    "code.",
    "pdb.",
    "sys._getframe",
    "sys.set_asyncgen_hooks",
    "signal.",
)

#: Every denial, whether or not user code swallowed the exception.
DENIALS: list[str] = []

#: Modules pulled in by interpreter start-up or by this file, which user code
#: would otherwise reach by name simply because they are already in
#: ``sys.modules`` — CPython does not re-fire the ``import`` audit event for a
#: cached module. Dropping them means ``import os`` has to go through the
#: loader again, where the hook refuses it. The audit hook already blocks what
#: these modules *do*; this closes the gap between blocking an operation and
#: being able to name the thing that performs it.
HIDDEN_MODULES = (
    "os",
    "sys",
    "io",
    "resource",
    "subprocess",
    "shutil",
    "pathlib",
    "tempfile",
    "importlib",
    "runpy",
    "gc",
    "inspect",
    "traceback",
    "linecache",
    "site",
    "sysconfig",
    "posix",
    "_io",
    "_socket",
    "socket",
    "ctypes",
    "_ctypes",
    "pickle",
    "marshal",
    "code",
    "codeop",
    "signal",
    "threading",
    "multiprocessing",
    "webbrowser",
    "platform",
    "getpass",
    "pwd",
    "grp",
)


class SandboxDenied(BaseException):
    """A sandboxed operation was refused by policy.

    Subclasses ``BaseException`` rather than ``Exception`` so that a strategy's
    ``except Exception`` does not quietly absorb it. A bare ``except:`` still
    can, which is why every denial is also recorded in :data:`DENIALS`.
    """


def _audit(event: str, args: tuple) -> None:
    if event == "import":
        module = args[0] if args else ""
        root = str(module).split(".")[0]
        if root not in ALLOWED_MODULES:
            DENIALS.append(f"import {module}")
            raise SandboxDenied(
                f"strategy code may not import {module!r}. Available: "
                f"{', '.join(sorted(ALLOWED_MODULES - {'app', '__future__'}))}"
            )
        return

    for prefix in BLOCKED_EVENTS:
        if event.startswith(prefix):
            detail = f"{event}{args[0]!r}" if args else event
            DENIALS.append(detail)
            raise SandboxDenied(
                f"strategy code may not perform {event!r}. The sandbox has no "
                "filesystem, no network and no subprocesses."
            )


def apply_limits(memory_mb: int, cpu_seconds: int) -> None:
    """Resource limits, applied before the hook so the hook can then forbid
    raising them again.

    ``RLIMIT_FSIZE`` of zero is a second layer under the audit hook's refusal
    of ``open``: even a file descriptor obtained some other way cannot be grown.
    It does not affect writing the result, because a pipe is not a file.
    """
    limit = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    except (ValueError, OSError):
        # Not settable to zero everywhere; the audit hook already refuses the
        # events that would need it, so this is hardening rather than the guard.
        pass


def hide_modules() -> None:
    """Make the already-imported dangerous modules unreachable by name.

    References this file already holds keep working — that is why the result is
    still writable afterwards — but ``import os`` now has to go through the
    loader, where the audit hook refuses it.
    """
    for name in HIDDEN_MODULES:
        _SYS.modules.pop(name, None)
    for name in list(_SYS.modules):
        if name.split(".")[0] in HIDDEN_MODULES:
            _SYS.modules.pop(name, None)


# --------------------------------------------------------------------------- #
# Task handlers
# --------------------------------------------------------------------------- #


def _exec_user_module(source: str) -> dict:
    """Compile and execute the user's source in a fresh namespace.

    ``__builtins__`` is left intact. Removing builtins is the traditional move
    and it is theatre: it is well known to be escapable through object
    traversal, and it breaks ordinary code for no real gain. The audit hook is
    the actual boundary, and it sits below Python rather than inside it.
    """
    namespace: dict = {
        "__name__": "user_strategy",
        "__builtins__": __builtins__,
        "Strategy": Strategy,
        "Signal": Signal,
        "Context": Context,
        "Bar": Bar,
        "PositionView": PositionView,
        "StrategyError": StrategyError,
        "LookaheadError": LookaheadError,
    }
    code = compile(source, "<strategy>", "exec")
    exec(code, namespace)  # noqa: S102 — the point of this module
    return namespace


def _find_strategy_class(namespace: dict) -> type:
    found = [
        obj
        for obj in namespace.values()
        if isinstance(obj, type) and issubclass(obj, Strategy) and obj is not Strategy
    ]
    if not found:
        raise StrategyError(
            "no Strategy subclass found. Define one, e.g. "
            "`class MyStrategy(Strategy): ...`"
        )
    if len(found) > 1:
        # Ambiguity here would mean picking one silently and backtesting code
        # the author did not mean to run.
        names = sorted(c.__name__ for c in found)
        raise StrategyError(
            f"found {len(found)} Strategy subclasses ({', '.join(names)}); "
            "define exactly one per strategy"
        )
    return found[0]


def task_describe(payload: dict) -> dict:
    """Compile the source and report the metadata the class declares.

    The parent validates what comes back into the real pydantic models — the
    sandbox reports, it does not decide what is valid.
    """
    namespace = _exec_user_module(payload["source"])
    cls = _find_strategy_class(namespace)
    instance = cls()
    instance.setup()
    return {
        "class_name": cls.__name__,
        "name": cls.declared_name(),
        "description": cls.description or "",
        "asset": cls.asset,
        "timeframe": cls.timeframe,
        "direction": cls.direction,
        "parameters": dict(cls.parameters),
        "indicators": [dict(i) for i in cls.indicators],
        "risk": dict(cls.risk),
        "costs": dict(cls.costs),
    }


def task_probe(payload: dict) -> dict:
    """Execute arbitrary source and report what happened. Tests only.

    The sandbox's guarantees are only worth what they are tested against, and
    testing them needs a way to run hostile code and see how it failed.
    """
    namespace = _exec_user_module(payload["source"])
    result = namespace.get("RESULT")
    return {"result": result if isinstance(result, (str, int, float, bool, type(None))) else repr(result)}


TASKS = {
    "describe": task_describe,
    "probe": task_probe,
}


def main() -> int:
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
    except ValueError as exc:
        _STDOUT.write(json.dumps({"ok": False, "error": "bad_request", "message": str(exc)}))
        return 2

    task = request.get("task", "")
    payload = request.get("payload", {})
    limits = request.get("limits", {})

    apply_limits(int(limits.get("memory_mb", 256)), int(limits.get("cpu_seconds", 10)))

    # Everything above this line runs with full privileges. Nothing below does.
    sys.addaudithook(_audit)
    hide_modules()

    try:
        handler = TASKS[task]
    except KeyError:
        response = {"ok": False, "error": "unknown_task", "message": f"unknown task {task!r}"}
    else:
        try:
            response = {"ok": True, "value": handler(payload)}
        except SandboxDenied as exc:
            response = {"ok": False, "error": "denied", "message": str(exc)}
        except MemoryError:
            response = {
                "ok": False,
                "error": "memory",
                "message": "strategy exceeded the sandbox memory limit",
            }
        except RecursionError:
            response = {
                "ok": False,
                "error": "user_error",
                "message": "strategy exceeded the recursion limit",
                "traceback": "",
            }
        except BaseException as exc:  # noqa: BLE001 — reported, never swallowed
            response = {
                "ok": False,
                "error": "user_error",
                "message": f"{type(exc).__name__}: {exc}",
                "traceback": _user_traceback(exc, str(payload.get("source", ""))),
            }

    response["denials"] = list(DENIALS)
    _STDOUT.write(json.dumps(response, default=str))
    _STDOUT.flush()
    return 0


def _user_traceback(exc: BaseException, source: str) -> str:
    """The traceback, trimmed to the frames inside the strategy.

    Built by walking the frames by hand rather than through
    ``traceback.format_exception``, for two reasons. The standard formatter
    reaches for ``linecache``, which opens files — inside the sandbox that is a
    denied operation, and an error report that itself raises is worse than no
    error report. And the strategy has no file to read anyway: its source is
    the string we were handed, so quoting the offending line means indexing
    into that, which is both possible here and impossible for linecache.

    Frames from the sandbox's own plumbing are dropped. A user staring at a
    mistake in their own code should not have to read past ours to find it.
    """
    lines = source.splitlines()
    out = ["Traceback (most recent call last):"]
    tb = exc.__traceback__
    shown = 0
    while tb is not None:
        frame = tb.tb_frame
        filename = frame.f_code.co_filename
        if filename == "<strategy>":
            lineno = tb.tb_lineno
            out.append(
                f'  File "<strategy>", line {lineno}, in {frame.f_code.co_name}'
            )
            if 1 <= lineno <= len(lines):
                out.append(f"    {lines[lineno - 1].strip()}")
            shown += 1
        tb = tb.tb_next
    out.append(f"{type(exc).__name__}: {exc}")
    return "\n".join(out) if shown else f"{type(exc).__name__}: {exc}"


if __name__ == "__main__":
    raise SystemExit(main())
