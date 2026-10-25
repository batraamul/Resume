"""Run slow operations (exports, conversions, backups, sync) off the interface thread."""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ris.errors import RISError

log = logging.getLogger(__name__)


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str, str)  # user message, technical detail (never shown with secrets)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.fn = fn
        self.signals = _Signals()
        self.setAutoDelete(True)

    def run(self) -> None:  # pragma: no cover - exercised through run_task
        try:
            try:
                result = self.fn()
            except RISError as exc:
                self.signals.failed.emit(exc.user_message, exc.detail)
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                log.error("Background task failed: %s", type(exc).__name__)
                self.signals.failed.emit(f"The operation could not be completed ({type(exc).__name__}).",
                                         "".join(traceback.format_exception_only(type(exc), exc)).strip())
            else:
                self.signals.done.emit(result)
        except RuntimeError:
            # The window that asked for this work was closed while it ran; nothing is waiting for the result.
            log.info("Background result discarded (receiver closed)")


_active: set[_Task] = set()


def run_task(fn: Callable[[], Any], on_done: Callable[[Any], None] | None = None,
             on_error: Callable[[str, str], None] | None = None, *, synchronous: bool = False) -> None:
    """Run ``fn`` in the thread pool; callbacks are delivered on the interface thread.

    ``synchronous=True`` runs inline (used by tests and when the pool is unavailable).
    """
    if synchronous:
        try:
            result = fn()
        except RISError as exc:
            if on_error:
                on_error(exc.user_message, exc.detail)
            return
        except Exception as exc:  # noqa: BLE001
            if on_error:
                on_error(f"The operation could not be completed ({type(exc).__name__}).", str(exc))
            return
        if on_done:
            on_done(result)
        return
    task = _Task(fn)
    _active.add(task)

    def _finish_ok(result: Any) -> None:
        _active.discard(task)
        if on_done:
            on_done(result)

    def _finish_err(msg: str, detail: str) -> None:
        _active.discard(task)
        if on_error:
            on_error(msg, detail)

    task.signals.done.connect(_finish_ok)
    task.signals.failed.connect(_finish_err)
    QThreadPool.globalInstance().start(task)


def wait_idle(timeout_ms: int = 60000) -> bool:
    return QThreadPool.globalInstance().waitForDone(timeout_ms)
