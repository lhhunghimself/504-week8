"""GameController — bridges the engine to all GUI widgets.

Contract: interfaces.md §7.3 (Team 3 — GameController).
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from main import Command, GameEngine, GameOutput, GameView

from gui.engine_worker import EngineWorker


class GameController(QObject):
    view_changed = pyqtSignal(object)    # GameView
    messages_ready = pyqtSignal(object)  # list[str]
    game_completed = pyqtSignal(object)  # dict (score metrics)
    hint_options_ready = pyqtSignal(object)  # list[dict]
    hint_result_ready = pyqtSignal(str)      # clue text

    def __init__(self, engine: GameEngine, *, threaded: bool = False,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._threaded = threaded
        self._worker: EngineWorker | None = None

        if threaded:
            self._worker = EngineWorker(engine)
            self._worker.result_ready.connect(self._handle_result)
            self._worker.error_occurred.connect(self._handle_error)
            self._worker.start()

    def initialize(self) -> None:
        view = self._engine.view()
        self.view_changed.emit(view)

    @pyqtSlot(object)
    def on_command(self, command: Command) -> None:
        if self._threaded and self._worker is not None:
            self._worker.submit_command(command)
        else:
            try:
                output = self._engine.handle(command)
                self._handle_result(output)
            except Exception as exc:
                self._handle_error(str(exc))

    def _handle_result(self, output: GameOutput) -> None:
        self.view_changed.emit(output.view)

        if output.messages:
            self.messages_ready.emit(output.messages)

        if output.hint_options is not None:
            self.hint_options_ready.emit(output.hint_options)
        else:
            for msg in output.messages:
                if isinstance(msg, str) and msg.startswith("Clue:"):
                    self.hint_result_ready.emit(msg)
                    break

        # Surface an explicit save indication to UI adapters.
        if output.did_persist:
            already_has_saved_msg = any(
                isinstance(m, str) and "saved" in m.lower()
                for m in output.messages
            )
            if not already_has_saved_msg:
                self.messages_ready.emit(["Progress saved."])

        if output.view.is_complete:
            metrics = self._load_completion_metrics()
            self.game_completed.emit(metrics)

    def _handle_error(self, error_msg: str) -> None:
        self.messages_ready.emit([f"Error: {error_msg}"])

    def _load_completion_metrics(self) -> dict:
        repo = getattr(self._engine, "repo", None)
        maze = getattr(self._engine, "maze", None)
        game_id = getattr(self._engine, "game_id", None)

        if repo is not None and hasattr(repo, "top_scores"):
            try:
                maze_id = getattr(maze, "maze_id", None)
                rows = repo.top_scores(maze_id=maze_id, limit=1000)
                for row in rows:
                    if row.get("game_id") == game_id:
                        metrics = row.get("metrics")
                        if isinstance(metrics, dict):
                            return metrics
            except Exception:
                pass

        # Fallback: derive a reasonable metrics payload from engine state.
        return {
            "elapsed_seconds": 0,
            "moves": getattr(self._engine, "_move_count", 0),
            "puzzles_solved": len(getattr(self._engine, "_solved_gates", [])),
            "hints_used": getattr(self._engine, "_hints_used", 0),
        }

    def shutdown(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker = None
