"""Percent and remaining time for a map batch row."""

from __future__ import annotations


def percent_done(done: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(100, int(done * 100 / total)))


def remaining_seconds(done: int, total: int, elapsed: float) -> float | None:
    """Seconds left at the rate so far. None until one spectrum has finished."""
    if done <= 0 or total <= 0 or elapsed <= 0:
        return None
    if done >= total:
        return 0.0
    return (total - done) * elapsed / done


def format_remaining(seconds: float | None) -> str:
    if seconds is None:
        return "estimating"
    whole = int(max(0, round(seconds)))
    if whole < 60:
        return f"{whole}s"
    minutes, _leftover = divmod(whole, 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if minutes == 0:
        return f"{hours} h"
    return f"{hours} h {minutes} min"


def fitting_label(done: int, total: int, eta_seconds: float | None) -> str:
    """Status text for one batch: ``42% · 14 min left``."""
    pct = percent_done(done, total)
    if done <= 0 or eta_seconds is None:
        return f"{pct}% · estimating"
    return f"{pct}% · {format_remaining(eta_seconds)} left"
