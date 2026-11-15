"""Fit folders of MCA files with PyMca's map batch.

PyMca's Batch Fitting window writes ``00001_to_<last>.h5`` in the sample
folder and peak images under ``IMAGES``. This calls that same fitter with
the file list, so it never opens the file dialog that freezes on thousands
of ``.mca`` files. The MCA folder and ``Older cfg used`` are only read.

Several sample folders fit at the same time. They share a process budget
that leaves a core free, and the fit processes run at low priority.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from PyMcaExpanded.schedule import (
    acquire_processes,
    default_fit_processes,
    limit_math_threads,
    lower_priority,
    machine_limit,
    plan_batches,
    release_processes,
)

MAP_PROCESSES = default_fit_processes()
OK = "OK"
PROBLEM = "problem"
SKIPPED = "already has results"
CANCELLED = "cancelled"
NOT_STARTED = "not started"

_SKIP_NAMES = {
    "mca",
    "images",
    "older cfg used",
    "configuration files for pymca",
    "fit",
    "html",
}
_PROTECTED = {"mca", "older cfg used"}
_OUTPUT_EXTENSIONS = {".h5", ".cfg", ".csv", ".dat", ".edf", ".tif", ".tiff"}
_NUMBER = re.compile(r"(\d+)")
_PROGRESS = None
_PROGRESS_CALLBACK = None
_CANCEL = None
_POOL_LOCK = threading.Lock()


def _init_progress(counter) -> None:
    global _PROGRESS
    _PROGRESS = counter
    limit_math_threads()
    lower_priority()


@dataclass(frozen=True)
class Sample:
    path: str
    has_results: bool
    mca_count: int
    existing_h5: str
    expected_h5: str


@dataclass
class MapResult:
    folder: str
    path: str
    mca_count: int
    h5_name: str
    status: str
    detail: str = ""


@dataclass
class MapProgress:
    index: int
    total: int
    folder: str
    spectra_done: int
    spectra_total: int
    message: str
    batches_running: int = 0


def discover_configs(root: str | Path) -> list[Path]:
    """``.cfg`` files in ``Configuration Files for PyMCA``, in name order.

    ``Older cfg used`` is a separate folder and is not included. The caller
    has to choose one file. A root with several configurations has no default.
    """
    folder = Path(root)
    library = _find_child(folder, "Configuration Files for PyMCA")
    if library is None or not library.is_dir():
        return []
    files = [path for path in library.iterdir() if path.is_file() and path.suffix.lower() == ".cfg"]
    files.sort(key=_natural_key)
    return files


def discover_samples(root: str | Path) -> list[Sample]:
    """Sample folders under ``root`` that contain an MCA directory.

    If ``root`` itself contains ``MCA``, it is the only sample.
    ``Older cfg used`` and ``Configuration Files for PyMCA`` are not samples.
    """
    folder = Path(root)
    if not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")
    own = _find_child(folder, "MCA")
    if own is not None and own.is_dir():
        return [inspect_sample(folder)]
    found: list[Sample] = []
    for child in folder.iterdir():
        if not child.is_dir() or child.name.lower() in _SKIP_NAMES:
            continue
        mca = _find_child(child, "MCA")
        if mca is not None and mca.is_dir():
            found.append(inspect_sample(child))
    found.sort(key=lambda sample: Path(sample.path).name.lower())
    return found


def inspect_sample(path: str | Path) -> Sample:
    folder = Path(path)
    files = mca_files(folder)
    expected = f"{output_root(files)}.h5" if files else ""
    return Sample(
        path=str(folder),
        has_results=has_results(folder),
        mca_count=len(files),
        existing_h5=_existing_h5(folder),
        expected_h5=expected,
    )


def mca_files(sample: str | Path) -> list[Path]:
    """``.mca`` files in the sample's MCA folder, in numeric name order."""
    folder = _find_child(Path(sample), "MCA")
    if folder is None or not folder.is_dir():
        return []
    files = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() == ".mca"]
    files.sort(key=_natural_key)
    return files


def has_results(sample: str | Path) -> bool:
    """True when the sample already has an IMAGES folder or a finished ``.h5``."""
    folder = Path(sample)
    images = _find_child(folder, "IMAGES")
    if images is not None and images.is_dir():
        return True
    return _existing_h5(folder) != ""


def output_root(files: list[Path] | list[str]) -> str:
    """PyMca's ``00001_to_<last>`` name for this file list."""
    from PyMca5.PyMcaPhysics.xrf.McaAdvancedFitBatch import getRootName

    names = [str(path) for path in files]
    if not names:
        raise ValueError("No MCA files.")
    return getRootName(names)


def batch_slices(n_files: int, workers: int) -> list[tuple[int, int, int, int, int, int | None]]:
    """How PyMca splits a map across processes.

    Each tuple is ``(file begin, file end offset, file step, mca offset, mca step, chunk)``.
    One process uses no chunk suffix. More processes use the same slicing as
    PyMca's Batch Fitting window.
    """
    if workers < 1:
        raise ValueError("Worker count must be at least 1.")
    if n_files < 1:
        return []
    if workers == 1:
        return [(0, 0, 1, 0, 1, None)]
    per_chunk = min((n_files + workers - 1) // workers, n_files)
    n_chunks = (n_files + per_chunk - 1) // per_chunk
    per_file = max(workers // n_chunks, 1)
    jobs: list[tuple[int, int, int, int, int, int | None]] = []
    for offset in range(per_file):
        for index in range(n_chunks):
            begin = index * per_chunk
            end = min(begin + per_chunk, n_files)
            if begin >= end:
                break
            jobs.append((begin, n_files - end, 1, offset, per_file, offset * n_chunks + index))
    return jobs


def run_maps(
    cfg: str,
    root: str | Path | None = None,
    folders: list[str] | None = None,
    workers: int = MAP_PROCESSES,
    overwrite: bool = False,
    progress=None,
    cancel: Event | None = None,
    process_limit: int | None = None,
) -> list[MapResult]:
    """Fit every sample that still needs a fit.

    Folders share ``workers`` fit processes and run together, up to the
    machine limit. One folder uses the whole count. Three folders of
    12,000 to 15,000 spectra each take an equal share. A folder that
    already has results is skipped unless ``overwrite`` is set. A missing
    or wrong output stops the queue after the folders already running
    finish. Later folders are reported as not started.
    """
    if workers < 1:
        raise ValueError("Worker count must be at least 1.")
    config = Path(cfg)
    if not config.is_file():
        raise FileNotFoundError(f"Configuration not found: {config}")
    try:
        import h5py  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("HDF5 output needs the h5py package.") from exc

    if folders is not None:
        samples = [inspect_sample(folder) for folder in folders]
    elif root is not None:
        samples = discover_samples(root)
    else:
        raise ValueError("Give a root folder or a list of sample folders.")

    limit = machine_limit() if process_limit is None else max(1, process_limit)
    budget = min(workers, limit)
    total = len(samples)
    results: list[MapResult | None] = [None] * total
    fit_indexes: list[int] = []
    for index, sample in enumerate(samples):
        name = Path(sample.path).name
        if cancel is not None and cancel.is_set():
            results[index] = _result(sample, CANCELLED, "Cancelled.")
            for later in range(index + 1, total):
                results[later] = _result(samples[later], NOT_STARTED, "Stopped.")
            break
        if sample.has_results and not overwrite:
            results[index] = _result(sample, SKIPPED, "")
            _emit(progress, index, total, name, 0, sample.mca_count, SKIPPED)
            continue
        blocked = _blocked(sample)
        if blocked:
            results[index] = _result(sample, PROBLEM, blocked)
            for later in range(index + 1, total):
                results[later] = _result(samples[later], NOT_STARTED, "Stopped after a problem.")
            break
        fit_indexes.append(index)

    cursor = 0
    stop_detail = ""
    while cursor < len(fit_indexes):
        if cancel is not None and cancel.is_set():
            stop_detail = "Stopped."
            break
        grants = plan_batches(len(fit_indexes) - cursor, budget)
        wave = fit_indexes[cursor : cursor + len(grants)]
        grant = acquire_processes(sum(grants), cancel, limit)
        if grant == 0:
            stop_detail = "Stopped."
            break
        outcomes: dict[int, str] = {}
        try:
            try:
                if len(wave) == 1:
                    outcomes = _fit_one(config, samples, wave[0], grants[0], progress, cancel, total)
                else:
                    outcomes = _fit_many(config, samples, wave, grants, progress, cancel, total)
            except Exception as exc:
                text = str(exc).strip() or exc.__class__.__name__
                outcomes = {index: text for index in wave}
        finally:
            release_processes(grant)
        wave_problem = False
        wave_cancel = False
        for index in wave:
            outcome = outcomes.get(index, "The fit did not finish.")
            sample = samples[index]
            name = Path(sample.path).name
            if outcome == "cancelled":
                results[index] = _result(sample, CANCELLED, "Cancelled.")
                wave_cancel = True
            elif outcome:
                results[index] = _result(sample, PROBLEM, outcome)
                wave_problem = True
            else:
                results[index] = _result(sample, OK, "")
                _emit(progress, index, total, name, sample.mca_count, sample.mca_count, OK, len(wave))
        cursor += len(wave)
        if wave_problem:
            stop_detail = "Stopped after a problem."
            break
        if wave_cancel:
            stop_detail = "Stopped."
            break

    for index in fit_indexes[cursor:]:
        if results[index] is None:
            results[index] = _result(samples[index], NOT_STARTED, stop_detail or "Stopped.")
    finished: list[MapResult] = []
    for index, result in enumerate(results):
        if result is None:
            result = _result(samples[index], NOT_STARTED, stop_detail or "Stopped.")
        finished.append(result)
    return finished


def format_table(results: list[MapResult]) -> str:
    rows = [("folder", "mca files", "output h5", "status")]
    for result in results:
        status = result.status
        if result.detail and result.status != OK:
            status = f"{result.status}: {result.detail}"
        rows.append((result.folder, str(result.mca_count), result.h5_name, status))
    widths = [max(len(row[column]) for row in rows) for column in range(4)]
    lines = []
    for index, row in enumerate(rows):
        lines.append(" | ".join(cell.ljust(widths[column]) for column, cell in enumerate(row)))
        if index == 0:
            lines.append("-+-".join("-" * width for width in widths))
    return "\n".join(lines)


def _blocked(sample: Sample) -> str:
    folder = Path(sample.path)
    mca = _find_child(folder, "MCA")
    if mca is None or not mca.is_dir():
        return "No MCA folder."
    if sample.mca_count == 0:
        return "No .mca files."
    if _same_directory(folder, mca):
        return "The output folder is the MCA folder."
    return ""


def _fit_one(config: Path, samples: list[Sample], index: int, grant: int, progress, cancel, total: int) -> dict[int, str]:
    sample = samples[index]
    name = Path(sample.path).name
    _emit(progress, index, total, name, 0, sample.mca_count, "fitting", 1)
    outcome = _fit_folder(
        str(config),
        Path(sample.path),
        grant,
        lambda done, folder_name=name, count=sample.mca_count, idx=index: _emit(
            progress, idx, total, folder_name, done, count, "fitting", 1
        ),
        cancel,
        together=False,
    )
    return {index: outcome}


def _fit_many(
    config: Path,
    samples: list[Sample],
    indexes: list[int],
    grants: list[int],
    progress,
    cancel,
    total: int,
) -> dict[int, str]:
    """Fit this wave together. Each folder has its own process pool."""
    running = len(indexes)
    outcomes: dict[int, str] = {}

    def run_one(index: int, grant: int) -> tuple[int, str]:
        sample = samples[index]
        name = Path(sample.path).name
        count = sample.mca_count
        _emit(progress, index, total, name, 0, count, "fitting", running)

        def on_progress(done: int, folder_name=name, spectra=count, idx=index) -> None:
            _emit(progress, idx, total, folder_name, done, spectra, "fitting", running)

        try:
            outcome = _fit_folder(str(config), Path(sample.path), grant, on_progress, cancel, together=True)
        except Exception as exc:
            outcome = str(exc).strip() or exc.__class__.__name__
        return index, outcome

    with ThreadPoolExecutor(max_workers=running) as pool:
        futures = [pool.submit(run_one, index, grant) for index, grant in zip(indexes, grants)]
        for future in as_completed(futures):
            index, outcome = future.result()
            outcomes[index] = outcome
    return outcomes


def _fit_folder(cfg: str, sample: Path, workers: int, progress, cancel: Event | None, together: bool = False) -> str:
    """Fit one sample. Return an empty string on success, otherwise the problem."""
    files = mca_files(sample)
    rootname = output_root(files)
    if _under(Path(cfg), _find_child(sample, "MCA")) or _under(Path(cfg), _find_child(sample, "Older cfg used")):
        return "The configuration file is inside a folder this run must not change."
    before_guard = _guard(sample)
    before_output = _output_files(sample)
    existed = {name: _find_child(sample, name) is not None for name in ("IMAGES", "FIT", "HTML")}
    try:
        error = _run_chunks(cfg, [str(path) for path in files], str(sample), workers, progress, cancel, together)
    except Exception as exc:
        error = str(exc).strip() or exc.__class__.__name__
    if error == "cancelled":
        _remove_new_files(sample, before_output)
        _remove_empty_dirs(sample, existed)
        return "cancelled"
    problems: list[str] = []
    if error:
        problems.append(error)
    else:
        problems.extend(_check_output(sample, files, rootname, cfg))
    if _guard(sample) != before_guard:
        problems.append("The MCA folder or Older cfg used changed during the fit.")
    if problems:
        _remove_new_files(sample, before_output)
        _remove_empty_dirs(sample, existed)
        return " ".join(problems)
    return ""


def _run_chunks(
    cfg: str,
    files: list[str],
    output: str,
    workers: int,
    progress,
    cancel: Event | None,
    together: bool = False,
) -> str:
    jobs = batch_slices(len(files), workers)
    # One folder, one process: fit here. PyMca does the same, and it avoids
    # starting a process for a small list. Folders running together each get
    # a process, including a one-process share, so they can run at low
    # priority without sharing this program's globals.
    if len(jobs) == 1 and not together:
        return _run_here(cfg, files, output, jobs[0], progress, cancel)
    ctx = mp.get_context("spawn")
    counter = ctx.Value("i", 0)
    with _POOL_LOCK:
        pool = ctx.Pool(processes=max(1, len(jobs)), initializer=_init_progress, initargs=(counter,))
    pending: list = []
    failed = ""
    try:
        for spec in jobs:
            pending.append(pool.apply_async(_fit_chunk, (cfg, files, output, spec)))
        while pending:
            if cancel is not None and cancel.is_set():
                failed = "cancelled"
                break
            ready = [job for job in pending if job.ready()]
            if not ready:
                progress(counter.value)
                time.sleep(0.05)
                continue
            for job in ready:
                pending.remove(job)
                try:
                    error = job.get()
                except Exception as exc:
                    error = str(exc).strip() or exc.__class__.__name__
                if error:
                    failed = error
                    pending.clear()
                    break
            progress(counter.value)
        if failed:
            return failed
        if any(spec[-1] is not None for spec in jobs):
            try:
                _merge(output, files)
            except Exception as exc:
                failed = str(exc).strip() or exc.__class__.__name__
                return failed
        return ""
    finally:
        if failed or pending:
            pool.terminate()
        else:
            pool.close()
        pool.join()


def _run_here(cfg: str, files: list[str], output: str, spec: tuple, progress, cancel: Event | None) -> str:
    """Fit one slice in this process. PyMca does the same when it uses one process."""
    if cancel is not None and cancel.is_set():
        return "cancelled"
    counter = _LocalCounter()
    global _PROGRESS, _PROGRESS_CALLBACK, _CANCEL
    previous_counter = _PROGRESS
    previous_callback = _PROGRESS_CALLBACK
    previous_cancel = _CANCEL
    _PROGRESS = counter
    _CANCEL = cancel
    _PROGRESS_CALLBACK = progress
    try:
        error = _fit_chunk(cfg, files, output, spec)
    finally:
        _PROGRESS = previous_counter
        _PROGRESS_CALLBACK = previous_callback
        _CANCEL = previous_cancel
    if cancel is not None and cancel.is_set():
        return "cancelled"
    return error or ""


class _LocalCounter:
    def __init__(self) -> None:
        self.value = 0
        self._lock = threading.Lock()

    def get_lock(self):
        return self._lock


def _fit_chunk(cfg: str, files: list[str], output: str, spec: tuple) -> str | None:
    from PyMca5.PyMcaPhysics.xrf.McaAdvancedFitBatch import McaAdvancedFitBatch

    begin, end_offset, file_step, mca_offset, mca_step, chunk = spec

    class _Counting(McaAdvancedFitBatch):
        def __init__(self, *args, **kwargs):
            self.current_file = None
            super().__init__(*args, **kwargs)

        def onNewFile(self, ffile, filelist):
            self.current_file = ffile
            super().onNewFile(ffile, filelist)

        def onMca(self, imca, nmca, filename=None, key=None, info=None):
            done = None
            if _PROGRESS is not None:
                with _PROGRESS.get_lock():
                    _PROGRESS.value += 1
                    done = _PROGRESS.value
            if _CANCEL is not None and _CANCEL.is_set():
                self.pleaseBreak = 1
            if _PROGRESS_CALLBACK is not None and done is not None:
                _PROGRESS_CALLBACK(done)

    kwargs = {
        "filelist": files,
        "outputdir": output,
        "roifit": 0,
        "roiwidth": 100,
        "overwrite": 1,
        "fitfiles": 0,
        "concentrations": 0,
        "fitimages": 1,
        "quiet": True,
        "filebeginoffset": begin,
        "fileendoffset": end_offset,
        "filestep": file_step,
        "mcaoffset": mca_offset,
        "mcastep": mca_step,
        "h5": 1,
        "csv": 1,
        "dat": 1,
        "edf": 1,
        "tif": 0,
        "multipage": 0,
        "diagnostics": 0,
    }
    if chunk is not None:
        kwargs["chunk"] = chunk
    batch = _Counting(cfg, **kwargs)
    try:
        batch.processList()
    except Exception as exc:
        text = str(exc).strip() or exc.__class__.__name__
        if batch.current_file:
            return f"Could not fit {batch.current_file}: {text}"
        return text
    return None


def _merge(output: str, files: list[str]) -> None:
    from PyMca5.PyMcaCore.PyMcaBatchBuildOutput import PyMcaBatchBuildOutput
    from PyMca5.PyMcaPhysics.xrf.McaAdvancedFitBatch import getRootName

    rootname = getRootName(files)
    work = PyMcaBatchBuildOutput(inputdir=output)
    work.buildOutput(basename=rootname, delete=True)
    images = os.path.join(output, "IMAGES")
    work.buildOutput(basename=rootname, inputdir=images, delete=True)


def _check_output(sample: Path, files: list[Path], rootname: str, cfg: str) -> list[str]:
    import h5py
    import numpy as np

    problems: list[str] = []
    h5_path = sample / f"{rootname}.h5"
    images = _find_child(sample, "IMAGES")
    if not h5_path.is_file():
        problems.append(f"Missing {h5_path.name}.")
    else:
        try:
            with h5py.File(h5_path, "r") as handle:
                image = _parameter_image(handle)
        except Exception as exc:
            image = None
            problems.append(f"{h5_path.name} could not be read ({exc}).")
        if image is None and not any(item.startswith(h5_path.name) for item in problems):
            problems.append(f"{h5_path.name} has no fit results.")
        elif image is not None:
            if image.shape[0] != len(files):
                problems.append(f"{h5_path.name} has {image.shape[0]} rows for {len(files)} MCA files.")
            rows = np.reshape(image, (image.shape[0], -1))
            if np.isnan(rows).all(axis=1).any():
                problems.append("One or more spectra were not fitted.")
    if images is None or not images.is_dir():
        problems.append("Missing IMAGES folder.")
    else:
        for suffix in (".cfg", ".csv", ".dat"):
            if not (images / f"{rootname}{suffix}").is_file():
                problems.append(f"Missing IMAGES/{rootname}{suffix}.")
        edfs = [
            path
            for path in images.iterdir()
            if path.is_file() and path.suffix.lower() == ".edf" and path.name.startswith(rootname) and "_partial" not in path.name.lower()
        ]
        if not edfs:
            problems.append("Missing EDF peak images.")
        for path in edfs:
            problem = _edf_problem(path, len(files))
            if problem:
                problems.append(problem)
        for suffix in (".csv", ".dat"):
            table = images / f"{rootname}{suffix}"
            if table.is_file():
                problem = _table_problem(table, len(files))
                if problem:
                    problems.append(problem)
        written_cfg = images / f"{rootname}.cfg"
        if written_cfg.is_file():
            problem = _config_problem(Path(cfg), written_cfg)
            if problem:
                problems.append(problem)
        tiffs = [path.name for path in images.iterdir() if path.suffix.lower() in {".tif", ".tiff"}]
        if tiffs:
            problems.append("TIFF files were written.")
    for name in ("FIT", "HTML"):
        extra = _find_child(sample, name)
        if extra is not None and extra.is_dir() and any(extra.iterdir()):
            problems.append(f"{extra.name} was written.")
    partials = [path.name for path in _partial_files(sample)]
    if partials:
        problems.append("Partial files were left behind.")
    if _protected_h5(sample):
        problems.append("An .h5 file was written inside MCA or Older cfg used.")
    return problems


def _table_problem(path: Path, n_files: int) -> str | None:
    """Each MCA file needs a row. A missing row means the table does not match the map."""
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError as exc:
        return f"{path.name} could not be read ({exc})."
    if len(lines) < 2:
        return f"{path.name} has no spectrum rows."
    indexes: set[int] = set()
    for line in lines[1:]:
        cell = line.split(";", 1)[0] if ";" in line else line.split()[0]
        cell = cell.strip().strip('"')
        try:
            indexes.add(int(float(cell)))
        except ValueError:
            return f"{path.name} has a row that is not a spectrum index."
    missing = [index for index in range(n_files) if index not in indexes]
    if missing:
        return f"{path.name} is missing {len(missing)} spectrum row(s)."
    return None


def _edf_problem(path: Path, n_files: int) -> str | None:
    """One image axis is the file count, so a short image is not a finished map."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return f"{path.name} could not be read ({exc})."
    end = raw.find(b"}")
    header = raw[:end if end > 0 else 4096].decode("ascii", "replace")
    dims: list[int] = []
    for key in ("Dim_1", "Dim_2"):
        marker = f"{key} ="
        if marker not in header:
            return f"{path.name} has no {key}."
        value = header.split(marker, 1)[1].split(";", 1)[0].strip()
        try:
            dims.append(int(value))
        except ValueError:
            return f"{path.name} has an unreadable {key}."
    if n_files not in dims:
        return f"{path.name} is {dims[0]} by {dims[1]} for {n_files} MCA files."
    return None


def _config_problem(source: Path, written: Path) -> str | None:
    """The saved configuration has to be the one selected for the run."""
    try:
        expected = _peak_map(source)
        actual = _peak_map(written)
    except Exception as exc:
        return f"{written.name} could not be compared with the selected configuration ({exc})."
    if actual != expected:
        return f"{written.name} does not match the selected configuration."
    return None


def _peak_map(path: Path) -> dict[str, str]:
    from PyMca5.PyMcaIO.ConfigDict import ConfigDict

    loaded = ConfigDict()
    loaded.read(str(path))
    peaks = loaded.get("peaks") or {}
    return {str(key): str(value).strip() for key, value in peaks.items()}


def _parameter_image(handle):
    found = None

    def visit(name, obj):
        nonlocal found
        if found is not None or not hasattr(obj, "shape") or getattr(obj, "ndim", 0) < 1:
            return
        if "parameters" in name.split("/") and getattr(obj.dtype, "kind", "") == "f":
            found = obj[()]

    handle.visititems(visit)
    return found


def _result(sample: Sample, status: str, detail: str) -> MapResult:
    return MapResult(
        folder=Path(sample.path).name,
        path=sample.path,
        mca_count=sample.mca_count,
        h5_name=sample.existing_h5 or sample.expected_h5,
        status=status,
        detail=detail,
    )


def _untouched(samples: list[Sample], status: str, detail: str) -> list[MapResult]:
    return [_result(sample, status, detail) for sample in samples]


def _emit(
    progress,
    index: int,
    total: int,
    folder: str,
    done: int,
    spectra: int,
    message: str,
    batches_running: int = 0,
) -> None:
    if progress is None:
        return
    progress(MapProgress(index, total, folder, done, spectra, message, batches_running))


def _existing_h5(sample: Path) -> str:
    try:
        names = [
            path.name
            for path in sample.iterdir()
            if path.is_file() and path.suffix.lower() == ".h5" and "_partial" not in path.name.lower()
        ]
    except OSError:
        return ""
    names.sort()
    return names[0] if names else ""


def _partial_files(sample: Path) -> list[Path]:
    found: list[Path] = []
    folders = [sample]
    images = _find_child(sample, "IMAGES")
    if images is not None and images.is_dir():
        folders.append(images)
    for folder in folders:
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        found.extend(path for path in entries if path.is_file() and "_partial" in path.name.lower())
    return found


def _output_files(sample: Path) -> set[Path]:
    found: set[Path] = set()
    try:
        entries = list(sample.iterdir())
    except OSError:
        return found
    for path in entries:
        if path.is_file() and path.suffix.lower() in _OUTPUT_EXTENSIONS:
            found.add(path.resolve())
    for name in ("IMAGES", "FIT", "HTML"):
        folder = _find_child(sample, name)
        if folder is None or not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.is_file():
                found.add(path.resolve())
    return found


def _remove_new_files(sample: Path, before: set[Path]) -> None:
    for path in _output_files(sample) - before:
        if _refuse_delete(sample, path):
            raise RuntimeError(f"Refusing to change {path}")
        path.unlink()


def _remove_empty_dirs(sample: Path, existed: dict[str, bool]) -> None:
    for name, was_there in existed.items():
        if was_there:
            continue
        folder = _find_child(sample, name)
        if folder is None or not folder.is_dir():
            continue
        if _refuse_delete(sample, folder):
            continue
        if any(path.is_file() for path in folder.rglob("*")):
            continue
        for path in sorted((item for item in folder.rglob("*") if item.is_dir()), reverse=True):
            path.rmdir()
        folder.rmdir()


def _guard(sample: Path) -> tuple:
    rows = []
    for name in ("MCA", "Older cfg used"):
        folder = _find_child(sample, name)
        if folder is None or not folder.exists():
            rows.append((name, False))
            continue
        files = []
        for path in folder.rglob("*"):
            if path.is_file():
                stat = path.stat()
                files.append((str(path.relative_to(folder)), stat.st_size, stat.st_mtime_ns))
        rows.append((name, tuple(sorted(files))))
    return tuple(rows)


def _refuse_delete(sample: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(sample.resolve())
    except ValueError:
        return True
    return bool(relative.parts) and relative.parts[0].lower() in _PROTECTED


def _under(path: Path, parent: Path | None) -> bool:
    if parent is None or not parent.exists():
        return False
    try:
        path.resolve().relative_to(parent.resolve())
    except (ValueError, OSError):
        return False
    return True


def _protected_h5(sample: Path) -> bool:
    for name in ("MCA", "Older cfg used"):
        folder = _find_child(sample, name)
        if folder is None or not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if path.is_file() and path.suffix.lower() == ".h5":
                return True
    return False


def _find_child(folder: Path, name: str) -> Path | None:
    direct = folder / name
    if direct.exists():
        return direct
    try:
        children = list(folder.iterdir())
    except OSError:
        return None
    for child in children:
        if child.name.lower() == name.lower():
            return child
    return None


def _same_directory(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _natural_key(path: Path):
    pieces = []
    for part in _NUMBER.split(path.name.lower()):
        if part.isdigit():
            pieces.append((0, int(part)))
        else:
            pieces.append((1, part))
    return tuple(pieces)
