"""Watchdog liveness guard, variant-free tier.

W1  a worker that stays alive leaves the body's result untouched and the poll stops
W2  a worker that dies triggers the abort action with the exit code and the description
"""

from __future__ import annotations

import threading
import time

from mathbook.watchdog import undertaker


def test_live_worker_leaves_the_body_alone():
    calls = []
    with undertaker(lambda: True, interval=0.01, _abort=calls.append):
        time.sleep(0.05)
        result = 41 + 1
    time.sleep(0.05)
    assert result == 42
    assert calls == []


def test_dead_worker_aborts_with_the_exit_code():
    calls = []
    fired = threading.Event()

    def abort(code):
        calls.append(code)
        fired.set()

    alive = {"state": True}
    with undertaker(
        lambda: alive["state"], diagnostic=lambda: "cell 13", interval=0.01, exit_code=7, _abort=abort
    ):
        alive["state"] = False
        assert fired.wait(2.0)
    assert calls == [7]
