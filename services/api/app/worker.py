"""Lightweight in-process job queue.

Long-running work (download, transcription, rendering) executes on daemon
worker threads so API requests stay responsive. Progress is persisted to the
database, which the frontend polls. Swappable for Celery/RQ in production —
the pipeline functions only depend on a job id.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("proclipper.worker")

_task_queue: "queue.Queue[Task]" = queue.Queue()
_started = False
_lock = threading.Lock()


@dataclass
class Task:
    fn: Callable[..., Any]
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    name: str = "task"


def _worker_loop(worker_id: int) -> None:
    while True:
        task = _task_queue.get()
        try:
            log.info("worker %d: starting %s", worker_id, task.name)
            task.fn(*task.args, **task.kwargs)
            log.info("worker %d: finished %s", worker_id, task.name)
        except Exception:
            log.exception("worker %d: task %s crashed", worker_id, task.name)
        finally:
            _task_queue.task_done()


def start_workers(count: int = 1) -> None:
    global _started
    with _lock:
        if _started:
            return
        for i in range(max(1, count)):
            t = threading.Thread(target=_worker_loop, args=(i,), daemon=True, name=f"proclipper-worker-{i}")
            t.start()
        _started = True


def enqueue(fn: Callable[..., Any], *args: Any, name: str = "task", **kwargs: Any) -> None:
    _task_queue.put(Task(fn=fn, args=args, kwargs=kwargs, name=name))


def pending_count() -> int:
    return _task_queue.qsize()
