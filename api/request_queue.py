"""Small in-process FIFO for expensive API work.

The API runs one Uvicorn worker in the supplied Docker setup. Serializing these
CPU- and provider-heavy operations protects shared model/cache state and keeps
bursts from exhausting the worker pool. This is intentionally not a durable
multi-process job broker; use Redis/Celery if the API is later scaled out.
"""

from collections import deque
from contextlib import contextmanager
import threading
from typing import Iterator


class QueueFull(Exception):
    """Raised when the bounded waiting queue is full."""


class FIFORequestQueue:
    def __init__(self, max_waiting: int = 8):
        self.max_waiting = max(1, max_waiting)
        self._condition = threading.Condition()
        self._waiting: deque[object] = deque()
        self._active = False
        self._completed = 0
        self._rejected = 0

    @contextmanager
    def slot(self) -> Iterator[None]:
        ticket = object()
        with self._condition:
            if len(self._waiting) >= self.max_waiting:
                self._rejected += 1
                raise QueueFull("The request queue is full. Please retry shortly.")
            self._waiting.append(ticket)
            try:
                while self._waiting[0] is not ticket or self._active:
                    self._condition.wait()
                self._waiting.popleft()
                self._active = True
            except BaseException:
                self._waiting.remove(ticket)
                self._condition.notify_all()
                raise
        try:
            yield
        finally:
            with self._condition:
                self._active = False
                self._completed += 1
                self._condition.notify_all()

    def snapshot(self) -> dict[str, int | bool]:
        with self._condition:
            return {
                "active": self._active,
                "waiting": len(self._waiting),
                "max_waiting": self.max_waiting,
                "completed": self._completed,
                "rejected": self._rejected,
            }
