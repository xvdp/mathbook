"""@xvdp

External worker watch to prevent blocking zero signal open sockets if proc worker dies.
Undertaker polls daemon thread life. On demise stderrs and terminates the caller.
Built and tested with jupyter notebook.
"""

from __future__ import annotations

from typing import Callable
import contextlib
import os
import sys
import threading


@contextlib.contextmanager
def undertaker(is_alive: Callable,
               diagnostic: Callable | None = None,
               interval: float = 10.0,
               exit_code: int = 3,
               _abort: object | None = None):
    r"""Guard blocking calls polling .is_alive(). Terminates zombies.

    Polls daemon thread on sec. intervals. If worker pops out, sends diagnostic() to stderr
    and ends process [default: os._exit(exit_code)] preventing hanging chads from blocking.

    Args:
        is_alive: callable, True while worker lives. Takes jupyter's KernelManager.is_alive().
        stderr: callable naming the worker diagnostic line. None prints generic.
        interval: seconds between polls.
        exit_code: abort process exit code.
        _abort: exit code abort action. If None, os._exit().

    Example:
        >>> with undertaker(manager.is_alive, lambda: f"cell {state['cell']}"):
        ...     client.execute()
    """
    abort = os._exit if _abort is None else _abort
    done = threading.Event()

    def watch():
        while not done.wait(interval):
            if not is_alive():
                _stderr = diagnostic() if diagnostic is not None else "Elvis"
                print(
                    f"watchdog: {_stderr} has left the building. Exit code {exit_code}",
                    file=sys.stderr,
                    flush=True,
                )
                abort(exit_code)
                return

    thread = threading.Thread(target=watch, name="undertaker", daemon=True)
    thread.start()
    try:
        yield
    finally:
        done.set()
