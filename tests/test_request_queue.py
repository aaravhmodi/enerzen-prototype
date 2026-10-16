import threading
import time

import pytest

from api.request_queue import FIFORequestQueue, QueueFull


def test_queue_runs_waiters_in_fifo_order_and_only_one_at_a_time():
    queue = FIFORequestQueue(max_waiting=2)
    first_entered = threading.Event()
    release_first = threading.Event()
    order = []
    active = 0
    max_active = 0
    guard = threading.Lock()

    def work(name):
        nonlocal active, max_active
        with queue.slot():
            with guard:
                active += 1
                max_active = max(max_active, active)
                order.append(name)
            if name == "first":
                first_entered.set()
                assert release_first.wait(timeout=2)
            with guard:
                active -= 1

    threads = [threading.Thread(target=work, args=(name,)) for name in ("first", "second", "third")]
    threads[0].start()
    assert first_entered.wait(timeout=2)
    threads[1].start()
    deadline = time.monotonic() + 2
    while queue.snapshot()["waiting"] < 1 and time.monotonic() < deadline:
        time.sleep(0.005)
    threads[2].start()
    deadline = time.monotonic() + 2
    while queue.snapshot()["waiting"] < 2 and time.monotonic() < deadline:
        time.sleep(0.005)

    with pytest.raises(QueueFull):
        with queue.slot():
            pass

    release_first.set()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()
    assert order == ["first", "second", "third"]
    assert max_active == 1
    assert queue.snapshot() == {
        "active": False, "waiting": 0, "max_waiting": 2, "completed": 3, "rejected": 1,
    }


def test_queue_releases_slot_when_work_raises():
    queue = FIFORequestQueue()
    with pytest.raises(RuntimeError):
        with queue.slot():
            raise RuntimeError("failed work")
    with queue.slot():
        assert queue.snapshot()["active"]
    assert queue.snapshot()["completed"] == 2
