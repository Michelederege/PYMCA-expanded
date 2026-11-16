import os
import threading

import pytest

from PyMcaExpanded.schedule import (
    acquire_processes,
    begin_fit_reservation,
    default_fit_processes,
    end_fit_reservation,
    machine_limit,
    physical_core_count,
    pin_fit_worker,
    plan_batches,
    processes_in_use,
    release_processes,
    reserved_ui_cores,
    worker_cpu_ids,
)


def test_plan_shares_a_budget_across_batches():
    assert plan_batches(1, 6) == [6]
    assert plan_batches(3, 6) == [2, 2, 2]
    assert plan_batches(3, 5) == [2, 2, 1]
    assert plan_batches(4, 6) == [2, 2, 1, 1]
    assert plan_batches(10, 6) == [1, 1, 1, 1, 1, 1]
    assert plan_batches(3, 2) == [1, 1]
    assert plan_batches(0, 6) == []
    with pytest.raises(ValueError):
        plan_batches(2, 0)


def test_twelve_physical_cores_do_not_become_twenty_two_processes(monkeypatch):
    groups = [[index * 2, index * 2 + 1] for index in range(12)]
    monkeypatch.setattr("PyMcaExpanded.schedule.topology_groups", lambda: groups)
    assert physical_core_count() == 12
    assert machine_limit() == 12
    assert reserved_ui_cores() == 2
    assert default_fit_processes() == 10
    assert plan_batches(5, default_fit_processes()) == [2, 2, 2, 2, 2]
    assert len(plan_batches(12, default_fit_processes())) == 10
    cpus = worker_cpu_ids(10, groups)
    assert cpus == [cpu for group in groups[2:] for cpu in group]
    assert 0 not in cpus and 1 not in cpus
    assert worker_cpu_ids(12, groups) is None


def test_unknown_topology_halves_a_large_logical_count(monkeypatch):
    monkeypatch.setattr("PyMcaExpanded.schedule.topology_groups", lambda: None)
    monkeypatch.setattr("PyMcaExpanded.schedule.os.cpu_count", lambda: 24)
    assert physical_core_count() == 12
    assert default_fit_processes() == 10
    assert worker_cpu_ids(10) is None


def test_live_machine_stays_within_its_cores():
    logical = os.cpu_count() or 1
    assert 1 <= default_fit_processes() <= machine_limit()
    assert machine_limit() == physical_core_count()
    assert machine_limit() <= logical


def test_reservation_is_cleared_after_the_fit(monkeypatch):
    groups = [[0, 1], [2, 3], [4, 5], [6, 7]]
    monkeypatch.setattr("PyMcaExpanded.schedule.topology_groups", lambda: groups)
    begin_fit_reservation(2)
    try:
        assert os.environ["XRFDESK_FIT_CPUS"] == "2,3,4,5,6,7"
    finally:
        end_fit_reservation()
    assert "XRFDESK_FIT_CPUS" not in os.environ


@pytest.mark.skipif(not hasattr(os, "sched_getaffinity"), reason="Affinity is checked on Linux.")
def test_pin_fit_worker_restores_to_the_same_cpus():
    previous = os.sched_getaffinity(0)
    os.environ["XRFDESK_FIT_CPUS"] = ",".join(str(cpu) for cpu in sorted(previous))
    try:
        pin_fit_worker()
        assert os.sched_getaffinity(0) == previous
    finally:
        os.sched_setaffinity(0, previous)
        os.environ.pop("XRFDESK_FIT_CPUS", None)


def test_cancel_does_not_take_a_process():
    cancel = threading.Event()
    cancel.set()
    assert acquire_processes(1, cancel) == 0
    assert processes_in_use() == 0


def test_a_second_batch_waits_until_a_process_is_free():
    hold = acquire_processes(machine_limit())
    started = threading.Event()
    entered = threading.Event()

    def waiter():
        entered.set()
        got = acquire_processes(1)
        try:
            if got:
                started.set()
        finally:
            if got:
                release_processes(got)

    thread = threading.Thread(target=waiter)
    try:
        thread.start()
        assert entered.wait(5)
        thread.join(0.3)
        assert thread.is_alive()
        assert not started.is_set()
    finally:
        release_processes(hold)
    thread.join(5)
    assert not thread.is_alive()
    assert started.is_set()
    assert processes_in_use() == 0
