"""EngineWorker — runs engine.handle() off the main thread.

Contract: interfaces.md §7.3 (Team 3 — EngineWorker).
"""
from __future__ import annotations

from PyQt6.QtCore import QMutex, QObject, QWaitCondition, pyqtSignal, pyqtSlot, QThread

from main import Command, GameOutput


class EngineWorker(QThread):
    result_ready = pyqtSignal(object)   # GameOutput
    error_occurred = pyqtSignal(str)

    def __init__(self, engine: object, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._mutex = QMutex()
        self._condition = QWaitCondition()
        self._queue: list[Command] = []
        self._running = True

    def run(self) -> None:
        while self._running:
            self._mutex.lock()
            while not self._queue and self._running:
                self._condition.wait(self._mutex)
            if not self._running:
                self._mutex.unlock()
                break
            cmd = self._queue.pop(0)
            self._mutex.unlock()

            try:
                output = self._engine.handle(cmd)
                self.result_ready.emit(output)
            except Exception as exc:
                self.error_occurred.emit(str(exc))

    @pyqtSlot(object)
    def submit_command(self, command: Command) -> None:
        self._mutex.lock()
        self._queue.append(command)
        self._mutex.unlock()
        self._condition.wakeOne()

    def stop(self) -> None:
        self._mutex.lock()
        self._running = False
        self._mutex.unlock()
        self._condition.wakeOne()
        self.wait()
