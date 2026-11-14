import os
import threading

import pytest

from xrfdesk.schedule import (
    acquire_processes,
    default_fit_processes,
    machine_limit,
    plan_batches,
    processes_in_use,
    release_processes,
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


def test_default_budget_leaves_a_core_free():
    cores = os.cpu_count() or 1
    assert 1 <= default_fit_processes() <= machine_limit()
    if cores <= 2:
        assert machine_limit() == 1
        assert default_fit_processes() == 1
    elif cores < 6:
        assert machine_limit() == cores - 1
        assert default_fit_processes() == cores - 1
    else:
        assert machine_limit() == cores - 1
        assert default_fit_processes() == cores - 2


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
