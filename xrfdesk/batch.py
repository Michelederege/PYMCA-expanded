"""Fit a list of spectra with one PyMca configuration.

The worker function is module-level so it can run in another process.
A failed file is reported and the rest of the list continues.
"""

from __future__ import annotations

import multiprocessing as mp
import os
from dataclasses import dataclass, field
from threading import Event

from xrfdesk.curves import curves_from_config
from xrfdesk.engine import FitOutcome, fit_spectrum
from xrfdesk.schedule import (
    acquire_processes,
    default_fit_processes,
    limit_math_threads,
    lower_priority,
    machine_limit,
    release_processes,
)
from xrfdesk.spectra import list_labels, load_spectrum

WAITING = "waiting"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"


@dataclass
class ScanResult:
    path: str
    sample: str
    status: str
    error: str | None = None
    areas: dict[str, float] = field(default_factory=dict)
    concentrations: dict[str, float] = field(default_factory=dict)
    chisq: float | None = None


def default_workers() -> int:
    return default_fit_processes()


def run_batch(
    paths: list[str],
    config: dict,
    workers: int = 1,
    progress=None,
    cancel: Event | None = None,
) -> list[ScanResult]:
    """Fit ``paths`` in order. Results are returned in that same order."""
    if workers < 1:
        raise ValueError("Worker count must be at least 1.")
    results: list[ScanResult | None] = [None] * len(paths)
    if not paths:
        return []
    if cancel is not None and cancel.is_set():
        labelled = [_cancelled(path) for path in paths]
        for result, label in zip(labelled, list_labels(paths)):
            result.sample = label
        return labelled

    for index, path in enumerate(paths):
        if progress:
            progress(index, WAITING, None)

    slots = min(workers, len(paths), machine_limit())
    grant = acquire_processes(slots, cancel)
    if grant == 0:
        for index, path in enumerate(paths):
            results[index] = _cancelled(path)
            if progress:
                progress(index, CANCELLED, results[index])
        return _labelled(paths, results)
    try:
        if grant == 1:
            _fit_locally(paths, config, results, progress, cancel)
            return _labelled(paths, results)

        ctx = mp.get_context("spawn")
        pool = ctx.Pool(processes=grant, initializer=_init_pool_worker)
        pending: dict[int, mp.pool.AsyncResult] = {}
        next_index = 0
        try:
            while next_index < len(paths) or pending:
                if cancel is not None and cancel.is_set():
                    pool.terminate()
                    for index in list(pending):
                        results[index] = _cancelled(paths[index])
                        if progress:
                            progress(index, CANCELLED, results[index])
                    pending.clear()
                    break
                while next_index < len(paths) and len(pending) < grant:
                    pending[next_index] = pool.apply_async(_fit_job, (paths[next_index], config))
                    if progress:
                        progress(next_index, RUNNING, None)
                    next_index += 1
                finished = [index for index, job in pending.items() if job.ready()]
                if not finished:
                    import time

                    time.sleep(0.02)
                    continue
                for index in finished:
                    job = pending.pop(index)
                    try:
                        payload = job.get()
                    except Exception as exc:
                        payload = {"ok": False, "error": str(exc), "sample": os.path.basename(paths[index])}
                    results[index] = _result_from_payload(paths[index], payload)
                    if progress:
                        progress(index, results[index].status, results[index])
        finally:
            if pending:
                pool.terminate()
            else:
                pool.close()
            pool.join()
        return _labelled(paths, results)
    finally:
        release_processes(grant)


def _fit_locally(paths, config, results, progress, cancel) -> None:
    """Fit in this process. One worker has no process to start."""
    _init_worker()
    for index, path in enumerate(paths):
        if cancel is not None and cancel.is_set():
            for remaining in range(index, len(paths)):
                results[remaining] = _cancelled(paths[remaining])
                if progress:
                    progress(remaining, CANCELLED, results[remaining])
            return
        if progress:
            progress(index, RUNNING, None)
        payload = _fit_job(path, config)
        results[index] = _result_from_payload(path, payload)
        if progress:
            progress(index, results[index].status, results[index])


def _labelled(paths: list[str], results: list[ScanResult | None]) -> list[ScanResult]:
    labels = list_labels(paths)
    for index, path in enumerate(paths):
        if results[index] is None:
            results[index] = _cancelled(path)
        results[index].sample = labels[index]  # type: ignore[index]
    return results  # type: ignore[return-value]


def _fit_job(path: str, config: dict) -> dict:
    try:
        spectrum = load_spectrum(path)
        outcome: FitOutcome = fit_spectrum(spectrum, config, curves_from_config(config))
        return {
            "ok": True,
            "sample": spectrum.name,
            "areas": outcome.areas,
            "concentrations": outcome.concentrations,
            "chisq": outcome.chisq,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "sample": os.path.basename(path)}


def _init_pool_worker() -> None:
    limit_math_threads()
    lower_priority()


def _init_worker() -> None:
    limit_math_threads()


def _result_from_payload(path: str, payload: dict) -> ScanResult:
    if not payload.get("ok"):
        return ScanResult(
            path=path,
            sample=payload.get("sample") or os.path.basename(path),
            status=FAILED,
            error=payload.get("error") or "The fit failed.",
        )
    return ScanResult(
        path=path,
        sample=payload["sample"],
        status=DONE,
        areas=payload["areas"],
        concentrations=payload["concentrations"],
        chisq=payload["chisq"],
    )


def _cancelled(path: str) -> ScanResult:
    return ScanResult(path=path, sample=os.path.basename(path), status=CANCELLED, error="Cancelled.")


def write_csv(path: str, results: list[ScanResult], elements: list[str], groups: list[str]) -> None:
    headers = ["sample", "status", "error", "chi_square", *elements, *[f"area:{group}" for group in groups]]
    lines = [",".join(headers)]
    for result in results:
        row = [
            result.sample,
            result.status,
            result.error or "",
            "" if result.chisq is None else f"{result.chisq:.6f}",
        ]
        for element in elements:
            value = result.concentrations.get(element)
            row.append("" if value is None else f"{value:.6f}")
        for group in groups:
            value = result.areas.get(group)
            row.append("" if value is None else f"{value:.6f}")
        lines.append(",".join(_csv_cell(value) for value in row))
    text = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _csv_cell(value: str) -> str:
    if any(mark in value for mark in (",", '"', "\n")):
        return '"' + value.replace('"', '""') + '"'
    return value
