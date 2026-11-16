"""How many fit processes may run, and at what priority.

A 12-core processor with hyper-threading reports 24 logical processors.
``os.cpu_count`` returns that 24. Starting one fit process per logical
processor runs more PyMca processes than the chip can feed. Those extra
processes fight over the same cores, the fits slow down, and the computer
stops responding.

The budget uses physical cores. Two of them stay free on a large machine,
and the fit processes are kept off those cores. They also run at low
priority, so Excel and a browser are scheduled ahead of a fit.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from threading import Condition, Event

_condition = Condition()
_used = 0
_CPU_DIR = re.compile(r"cpu(\d+)$")


def topology_groups() -> list[list[int]] | None:
    """Logical CPUs grouped by physical core, or None when the OS does not say.

    Each inner list is the hyper-threads of one core. The groups are in
    package and core order, so the first groups are the ones left free.
    """
    readers = (_linux_groups, _windows_groups)
    for reader in readers:
        try:
            groups = reader()
        except (OSError, AttributeError, ValueError):
            groups = None
        if not groups:
            continue
        allowed = _allowed_cpus()
        if allowed is not None:
            groups = [[cpu for cpu in group if cpu in allowed] for group in groups]
            groups = [group for group in groups if group]
        if not groups:
            continue
        seen = sum(len(group) for group in groups)
        logical = os.cpu_count() or seen
        # A partial mask (more than 64 logical CPUs on Windows) is not safe to pin.
        if seen < logical:
            return None
        return groups
    return None


def physical_core_count() -> int:
    """Physical cores this process is allowed to run on.

    When the topology cannot be read, a large even logical count is treated
    as two threads per core. That under-fills a machine only when the OS
    hid the topology. It does not start two fit processes per core.
    """
    groups = topology_groups()
    if groups:
        return len(groups)
    logical = os.cpu_count() or 1
    if logical >= 8 and logical % 2 == 0:
        return logical // 2
    return max(1, logical)


def reserved_ui_cores(physical: int | None = None) -> int:
    """Cores kept free of fit processes so the machine stays usable.

    Eight or more physical cores keep two free. Smaller machines keep one.
    A single-core machine has nothing to reserve.
    """
    count = physical_core_count() if physical is None else physical
    if count >= 8:
        return 2
    if count >= 2:
        return 1
    return 0


def machine_limit() -> int:
    """Most fit processes that still match the physical cores.

    The cap is one process per physical core. Hyper-threads do not add
    processes. The spin box stops here. The default leaves cores free on
    top of this cap.
    """
    return max(1, physical_core_count())


def default_fit_processes() -> int:
    """Process budget for one Start.

    A 12-core, 24-thread processor defaults to 10 fit processes. The two
    cores that are left out stay available for this window, Excel, and a
    browser. Two cores or fewer keep a single fit process.
    """
    physical = physical_core_count()
    return max(1, physical - reserved_ui_cores(physical))


def worker_cpu_ids(requested: int, groups: list[list[int]] | None = None) -> list[int] | None:
    """Logical CPUs a fit process may use, or None when it may use every core.

    The reserved cores are left out while ``requested`` still fits on the
    rest. A request for every physical core uses every core: the spin box
    is how someone chooses a full machine when they are not using it.
    """
    if groups is None:
        groups = topology_groups()
    if not groups:
        return None
    physical = len(groups)
    reserve = reserved_ui_cores(physical)
    if requested > max(1, physical - reserve):
        reserve = 0
    if reserve <= 0:
        return None
    return [cpu for group in groups[reserve:] for cpu in group]


def begin_fit_reservation(requested: int) -> None:
    """Publish the CPUs fit processes may use. The window process is not pinned.

    Child processes read ``XRFDESK_FIT_CPUS`` when they start. Leaving this
    process on the full set means a one-process fit, which runs here, can
    still be scheduled. Ending the reservation clears the variable.
    """
    end_fit_reservation()
    cpus = worker_cpu_ids(max(1, int(requested)))
    if not cpus:
        return
    os.environ["XRFDESK_FIT_CPUS"] = ",".join(str(cpu) for cpu in cpus)


def end_fit_reservation() -> None:
    """Allow later fits to choose their own CPUs."""
    os.environ.pop("XRFDESK_FIT_CPUS", None)


def pin_fit_worker() -> None:
    """Keep this fit process off the cores reserved for other programs."""
    raw = os.environ.get("XRFDESK_FIT_CPUS", "")
    cpus = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            cpus.append(int(part))
    if not cpus:
        return
    try:
        _set_affinity(cpus)
    except (OSError, AttributeError):
        return


def plan_batches(n_batches: int, budget: int) -> list[int]:
    """How many fit processes each simultaneous batch gets.

    One batch uses the whole budget. Several batches share it evenly and
    run together. When there are more batches than processes, the extra
    batches wait for the next turn. A budget of 10 with five batches is
    ``[2, 2, 2, 2, 2]``. A budget of 10 with twelve batches starts ten of them.
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


def _linux_groups() -> list[list[int]] | None:
    if sys.platform == "win32":
        return None
    base = Path("/sys/devices/system/cpu")
    if not base.is_dir():
        return None
    found: dict[tuple[str, str], list[int]] = {}
    for cpu_dir in base.iterdir():
        match = _CPU_DIR.fullmatch(cpu_dir.name)
        if match is None or not cpu_dir.is_dir():
            continue
        package = cpu_dir / "topology" / "physical_package_id"
        core = cpu_dir / "topology" / "core_id"
        if not package.is_file() or not core.is_file():
            return None
        key = (package.read_text(encoding="ascii").strip(), core.read_text(encoding="ascii").strip())
        found.setdefault(key, []).append(int(match.group(1)))
    if not found:
        return None
    return [sorted(cpus) for _key, cpus in sorted(found.items())]


def _windows_groups() -> list[list[int]] | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class _ProcessorCore(ctypes.Structure):
        _fields_ = [("Flags", wintypes.BYTE)]

    class _NumaNode(ctypes.Structure):
        _fields_ = [("NodeNumber", wintypes.DWORD)]

    class _Cache(ctypes.Structure):
        _fields_ = [
            ("Level", wintypes.BYTE),
            ("Associativity", wintypes.BYTE),
            ("LineSize", wintypes.WORD),
            ("Size", wintypes.DWORD),
            ("Type", wintypes.DWORD),
        ]

    class _Union(ctypes.Union):
        _fields_ = [
            ("ProcessorCore", _ProcessorCore),
            ("NumaNode", _NumaNode),
            ("Cache", _Cache),
            ("Reserved", ctypes.c_ulonglong * 2),
        ]

    class _Info(ctypes.Structure):
        _fields_ = [
            ("ProcessorMask", ctypes.c_size_t),
            ("Relationship", wintypes.DWORD),
            ("Payload", _Union),
        ]

    kernel = ctypes.windll.kernel32
    get_info = kernel.GetLogicalProcessorInformation
    get_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    get_info.restype = wintypes.BOOL
    length = wintypes.DWORD(0)
    get_info(None, ctypes.byref(length))
    if length.value <= 0:
        return None
    buffer = ctypes.create_string_buffer(length.value)
    if not get_info(buffer, ctypes.byref(length)):
        return None
    count = length.value // ctypes.sizeof(_Info)
    rows = ctypes.cast(buffer, ctypes.POINTER(_Info))
    groups: list[list[int]] = []
    for index in range(count):
        row = rows[index]
        if row.Relationship != 0:
            continue
        mask = int(row.ProcessorMask)
        cpus = [bit for bit in range(mask.bit_length()) if mask & (1 << bit)]
        if cpus:
            groups.append(cpus)
    return groups or None


def _allowed_cpus() -> set[int] | None:
    try:
        if sys.platform == "win32":
            return _windows_allowed_cpus()
        return set(os.sched_getaffinity(0))
    except (OSError, AttributeError):
        return None


def _windows_allowed_cpus() -> set[int] | None:
    import ctypes
    from ctypes import wintypes

    process = ctypes.windll.kernel32.GetCurrentProcess()
    process_mask = ctypes.c_size_t()
    system_mask = ctypes.c_size_t()
    ok = ctypes.windll.kernel32.GetProcessAffinityMask(
        process,
        ctypes.byref(process_mask),
        ctypes.byref(system_mask),
    )
    if not ok:
        return None
    mask = int(process_mask.value)
    return {bit for bit in range(mask.bit_length()) if mask & (1 << bit)}


def _set_affinity(cpus: list[int]) -> None:
    if sys.platform == "win32":
        import ctypes

        mask = 0
        for cpu in cpus:
            if cpu < 0 or cpu >= 64:
                raise OSError("Affinity covers the first 64 logical processors.")
            mask |= 1 << cpu
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        if not ctypes.windll.kernel32.SetProcessAffinityMask(handle, ctypes.c_size_t(mask)):
            raise OSError("Could not set the fit process affinity.")
        return
    os.sched_setaffinity(0, set(cpus))
