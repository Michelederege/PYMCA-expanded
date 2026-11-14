"""How many fit processes may run, and at what priority.

A batch of 12,000 to 15,000 spectra is large enough that three of them have
to share the machine. The budget leaves a core free. Fit processes run at
low priority, so Excel and a browser get the CPU while a person is using
them, and the fit still gets it when those programs are idle.
"""

from __future__ import annotations

import os
import sys
from threading import Condition, Event

_condition = Condition()
_used = 0


def machine_limit() -> int:
    """Most fit processes that still leave the computer usable.

    Two cores or fewer keep a single fit process. A larger machine keeps
    one core free for Excel, a browser, and this program's window.
    """
    cores = os.cpu_count() or 1
    if cores <= 2:
        return 1
    return cores - 1


def default_fit_processes() -> int:
    """Process budget for one Start.

    Four cores leave one free, which is enough for three batches at once.
    Six or more cores leave two free.
    """
    cores = os.cpu_count() or 1
    if cores <= 2:
        return 1
    if cores < 6:
        return cores - 1
    return cores - 2


def plan_batches(n_batches: int, budget: int) -> list[int]:
    """How many fit processes each simultaneous batch gets.

    One batch uses the whole budget. Several batches share it evenly and
    run together. When there are more batches than processes, the extra
    batches wait for the next turn. A budget of 6 with three batches is
    ``[2, 2, 2]``. A budget of 6 with ten batches starts six of them.
    """
    if n_batches < 1:
        return []
    if budget < 1:
        raise ValueError("Process count must be at least 1.")
    if n_batches == 1:
        return [budget]
    parallel = min(n_batches, budget)
    base, extra = divmod(budget, parallel)
    return [base + (1 if index < extra else 0) for index in range(parallel)]


def acquire_processes(count: int, cancel: Event | None = None, limit: int | None = None) -> int:
    """Reserve ``count`` fit processes. Return 0 when ``cancel`` is set.

    The returned number is what the caller must release. It is never larger
    than the limit. Callers wait while another batch is using the machine.
    """
    global _used
    requested = max(1, int(count))
    with _condition:
        cap = machine_limit() if limit is None else max(1, int(limit))
        requested = min(requested, cap)
        while _used + requested > cap:
            if cancel is not None and cancel.is_set():
                return 0
            _condition.wait(timeout=0.2)
        if cancel is not None and cancel.is_set():
            return 0
        _used += requested
        return requested


def release_processes(count: int) -> None:
    """Return reserved fit processes so a waiting batch can start."""
    global _used
    with _condition:
        _used = max(0, _used - max(0, int(count)))
        _condition.notify_all()


def processes_in_use() -> int:
    with _condition:
        return _used


def limit_math_threads() -> None:
    """One math thread per fit process, unless the environment already chose one.

    Parallel fits stay comparable to a one-process fit. Extra BLAS threads
    on top of several fit processes would take the cores that were left free.
    """
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(name, "1")


def lower_priority() -> None:
    """Let Excel and a browser run ahead of this fit process.

    This is for a worker process only. Lowering priority in the program
    that owns the window would make the window itself sluggish.
    """
    try:
        if sys.platform == "win32":
            import ctypes

            # BELOW_NORMAL_PRIORITY_CLASS. Idle priority can stall the fit.
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.kernel32.SetPriorityClass(handle, 0x00004000)
        else:
            os.nice(10)
    except (OSError, AttributeError):
        return
