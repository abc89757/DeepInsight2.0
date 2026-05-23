from __future__ import annotations

import threading
from typing import Dict


class TaskCancelled(RuntimeError):
    """Raised when a running analysis task has been cancelled."""


_CANCEL_EVENTS: Dict[str, threading.Event] = {}
_LOCK = threading.Lock()


def register_task(task_id: str) -> threading.Event:
    """Create or reset the cancellation signal for one task."""
    with _LOCK:
        event = _CANCEL_EVENTS.get(task_id)
        if event is None:
            event = threading.Event()
            _CANCEL_EVENTS[task_id] = event
        else:
            event.clear()
        return event


def request_task_cancel(task_id: str) -> None:
    """Mark one running task as cancelled."""
    with _LOCK:
        event = _CANCEL_EVENTS.get(task_id)
        if event is None:
            event = threading.Event()
            _CANCEL_EVENTS[task_id] = event
        event.set()


def is_task_cancelled(task_id: str | None) -> bool:
    """Return whether a task has been cancelled."""
    if not task_id:
        return False
    with _LOCK:
        event = _CANCEL_EVENTS.get(task_id)
        return bool(event and event.is_set())


def raise_if_task_cancelled(task_id: str | None) -> None:
    """Stop execution if the given task has been cancelled."""
    if is_task_cancelled(task_id):
        raise TaskCancelled(f"任务 {task_id} 已取消。")


def cleanup_task_cancel(task_id: str) -> None:
    """Remove the cancellation signal once a task runner has exited."""
    with _LOCK:
        _CANCEL_EVENTS.pop(task_id, None)
