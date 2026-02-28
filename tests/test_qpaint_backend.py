"""Tests for the QPainter pre-rendered dungeon-crawler backend."""
from __future__ import annotations

import pytest
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QWidget

from gui.renderers.qpaint_backend import (
    QPaintBackend,
    QPaintViewport,
    _Cell,
    _Grid,
    render_view,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_snapshot() -> dict:
    """3x3 maze with start at (0,0), exit at (2,2), gate at (1,1)."""
    cells = []
    for r in range(3):
        for c in range(3):
            kind = "normal"
            is_player = (r == 0 and c == 0)
            has_gate = (r == 1 and c == 1)
            if r == 0 and c == 0:
                kind = "start"
            elif r == 2 and c == 2:
                kind = "exit"
            connections = []
            if r == 0 and c == 0:
                connections = ["E", "S"]
            elif r == 0 and c == 1:
                connections = ["W", "S"]
            elif r == 1 and c == 0:
                connections = ["N", "S"]
            elif r == 1 and c == 1:
                connections = ["N", "E"]
            elif r == 1 and c == 2:
                connections = ["W", "S"]
            elif r == 2 and c == 0:
                connections = ["N"]
            elif r == 2 and c == 2:
                connections = ["N"]
            cells.append({
                "row": r, "col": c, "kind": kind,
                "visible": True, "is_player": is_player,
                "has_gate": has_gate, "solved": False,
                "connections": connections,
            })
    return {"width": 3, "height": 3, "cells": cells}


# ---------------------------------------------------------------------------
# _Grid unit tests
# ---------------------------------------------------------------------------

class TestGrid:
    def test_dimensions(self):
        snap = _minimal_snapshot()
        grid = _Grid(snap)
        assert grid.width == 3
        assert grid.height == 3

    def test_cell_retrieval(self):
        grid = _Grid(_minimal_snapshot())
        cell = grid.cell(0, 0)
        assert cell is not None
        assert cell.kind == "start"
        assert cell.visible is True
        assert cell.is_player is True

    def test_out_of_bounds_returns_none(self):
        grid = _Grid(_minimal_snapshot())
        assert grid.cell(-1, 0) is None
        assert grid.cell(5, 5) is None

    def test_has_wall(self):
        grid = _Grid(_minimal_snapshot())
        assert grid.has_wall(0, 0, "N") is True
        assert grid.has_wall(0, 0, "W") is True
        assert grid.has_wall(0, 0, "E") is False
        assert grid.has_wall(0, 0, "S") is False


# ---------------------------------------------------------------------------
# render_view tests
# ---------------------------------------------------------------------------

class TestRenderView:
    def test_returns_qpixmap(self, qapp):
        grid = _Grid(_minimal_snapshot())
        pm = render_view(grid, 0, 0, "S")
        assert isinstance(pm, QPixmap)
        assert not pm.isNull()
        assert pm.width() == 640
        assert pm.height() == 480

    def test_all_four_facings(self, qapp):
        grid = _Grid(_minimal_snapshot())
        for facing in ("N", "S", "E", "W"):
            pm = render_view(grid, 0, 0, facing)
            assert isinstance(pm, QPixmap)
            assert not pm.isNull()

    def test_different_cell_types(self, qapp):
        grid = _Grid(_minimal_snapshot())
        pm_start = render_view(grid, 0, 0, "S")
        pm_gate = render_view(grid, 1, 1, "N")
        pm_exit = render_view(grid, 2, 2, "N")
        for pm in (pm_start, pm_gate, pm_exit):
            assert not pm.isNull()

    def test_render_for_all_visible_cells(self, qapp):
        grid = _Grid(_minimal_snapshot())
        for (r, c), cell in grid._cells.items():
            if cell.visible:
                for facing in ("N", "S", "E", "W"):
                    pm = render_view(grid, r, c, facing)
                    assert not pm.isNull(), f"Failed for ({r},{c},{facing})"


# ---------------------------------------------------------------------------
# QPaintBackend lifecycle tests
# ---------------------------------------------------------------------------

class TestQPaintBackendLifecycle:
    def test_initial_state(self):
        backend = QPaintBackend()
        assert backend.is_ready() is False
        assert backend._current_pixmap is None

    def test_start_creates_viewport(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        assert backend.is_ready() is True
        assert backend._viewport is not None
        assert isinstance(backend._viewport, QPaintViewport)

    def test_stop_clears_state(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.stop()
        assert backend.is_ready() is False
        assert backend._viewport is None

    def test_double_start_is_safe(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.start(parent)
        assert backend.is_ready() is True


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------

class TestViewCache:
    def test_cache_populated_on_maze_update(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)

        snap = _minimal_snapshot()
        backend.send_maze_update(snap)

        # Current view is rendered immediately; adjacent views are queued
        # for background rendering via QTimer.  Process pending events so
        # the pre-render timers fire.
        qtbot.waitUntil(lambda: len(backend._pending_prerender) == 0, timeout=5000)

        # At minimum the current view + adjacent views should be cached.
        assert len(backend._view_cache) >= 1
        # Current view must be present.
        key = (backend._player_row, backend._player_col, backend._facing_str)
        assert key in backend._view_cache

    def test_cache_entries_are_pixmaps(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        # Let background pre-rendering finish.
        qtbot.waitUntil(lambda: len(backend._pending_prerender) == 0, timeout=5000)

        assert len(backend._view_cache) >= 1
        for key, pm in backend._view_cache.items():
            assert isinstance(pm, QPixmap), f"Key {key} is not a QPixmap"
            assert not pm.isNull(), f"Key {key} is null"

    def test_cache_cleared_on_new_snapshot(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)

        backend.send_maze_update(_minimal_snapshot())
        first_cache_size = len(backend._view_cache)

        backend.send_maze_update(_minimal_snapshot())
        assert len(backend._view_cache) == first_cache_size

    def test_send_maze_update_before_start(self, qapp):
        """Sending data before start should buffer it."""
        backend = QPaintBackend()
        snap = _minimal_snapshot()
        backend.send_maze_update(snap)
        assert backend._current_snapshot is not None
        assert len(backend._view_cache) > 0

    def test_cache_rebuilt_on_start_if_snapshot_buffered(self, qtbot):
        """If snapshot was sent before start, cache should be built on start."""
        backend = QPaintBackend()
        snap = _minimal_snapshot()
        backend.send_maze_update(snap)

        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)

        assert len(backend._view_cache) > 0
        assert backend._current_pixmap is not None


# ---------------------------------------------------------------------------
# Player position + facing tests
# ---------------------------------------------------------------------------

class TestPlayerTracking:
    def test_player_position_from_snapshot(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        assert backend._player_row == 0
        assert backend._player_col == 0

    def test_send_highlight_player(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        backend.send_highlight_player(1, 1)
        assert backend._player_row == 1
        assert backend._player_col == 1

    def test_send_view_direction(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        backend.send_view_direction("N")
        assert backend._facing_str == "N"

        backend.send_view_direction("E")
        assert backend._facing_str == "E"


# ---------------------------------------------------------------------------
# Key injection tests
# ---------------------------------------------------------------------------

class TestKeyInjection:
    def test_turn_left(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        backend.send_view_direction("N")
        backend.inject_key("a", pressed=True)
        assert backend._facing_str == "W"

    def test_turn_right(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        backend.send_view_direction("N")
        backend.inject_key("d", pressed=True)
        assert backend._facing_str == "E"

    def test_forward_emits_direction(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        emitted = []
        backend.on_direction(lambda d: emitted.append(d))
        backend.send_view_direction("S")
        backend.inject_key("w", pressed=True)
        assert emitted == ["S"]

    def test_backward_emits_opposite_direction(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        emitted = []
        backend.on_direction(lambda d: emitted.append(d))
        backend.send_view_direction("N")
        backend.inject_key("s", pressed=True)
        assert emitted == ["S"]

    def test_key_release_ignored(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        backend.send_view_direction("N")
        backend.inject_key("a", pressed=False)
        assert backend._facing_str == "N"

    def test_unknown_key_ignored(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        backend.send_view_direction("N")
        backend.inject_key("x", pressed=True)
        assert backend._facing_str == "N"

    def test_facing_callback_fires_on_turn(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        facings = []
        backend.on_facing(lambda d: facings.append(d))
        backend.send_view_direction("N")
        backend.inject_key("a", pressed=True)
        assert "W" in facings

    def test_arrow_keys_work(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        backend.send_view_direction("N")
        backend.inject_key("arrow_left", pressed=True)
        assert backend._facing_str == "W"

        backend.inject_key("arrow_right", pressed=True)
        assert backend._facing_str == "N"


# ---------------------------------------------------------------------------
# QPaintViewport widget tests
# ---------------------------------------------------------------------------

class TestQPaintViewport:
    def test_viewport_paints_without_error(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)
        backend.send_maze_update(_minimal_snapshot())

        viewport = backend._viewport
        assert viewport is not None
        viewport.resize(640, 480)
        viewport.repaint()

    def test_viewport_paints_with_no_pixmap(self, qtbot):
        backend = QPaintBackend()
        parent = QWidget()
        qtbot.addWidget(parent)
        parent.show()
        backend.start(parent)

        viewport = backend._viewport
        assert viewport is not None
        viewport.repaint()


# ---------------------------------------------------------------------------
# Integration: gui_main wiring for qpaint renderer
# ---------------------------------------------------------------------------

class TestGuiMainQpaintWiring:
    def test_mainwindow_qpaint_renderer(self, qtbot, monkeypatch):
        """QPaint renderer path creates proper viewport and canvas."""
        from PyQt6.QtCore import QObject, pyqtSignal

        import gui_main

        class _FakeController(QObject):
            view_changed = pyqtSignal(object)
            messages_ready = pyqtSignal(list)
            hint_options_ready = pyqtSignal(list)
            hint_result_ready = pyqtSignal(str)
            game_completed = pyqtSignal(dict)
            def on_command(self, _command): pass

        class _FakeCanvas(QWidget):
            direction_clicked = pyqtSignal(str)
            godot_process_started = pyqtSignal(int)
            facing_changed = pyqtSignal(str)
            def __init__(self, backend):
                super().__init__()
                self._backend = backend
            def update_maze(self, _snap): pass
            def highlight_player(self, _pos): pass
            def set_view_direction(self, _d): pass
            def facing_direction(self): return "S"

        monkeypatch.setattr(gui_main, "FormsPanel", None)
        monkeypatch.setattr(gui_main, "PuzzleDialog", None)
        monkeypatch.setattr(gui_main, "StatusBar", None)
        monkeypatch.setattr(gui_main, "ScoreBoard", None)
        monkeypatch.setattr(gui_main, "MazeCanvas", _FakeCanvas)

        backend = QPaintBackend()

        def _fake_create_qpaint_canvas(self):
            self._qpaint_viewport = QWidget(self._viewport_host)
            return _FakeCanvas(backend)

        monkeypatch.setattr(
            gui_main.MainWindow, "_create_qpaint_canvas",
            _fake_create_qpaint_canvas,
        )

        win = gui_main.MainWindow(
            _FakeController(),
            repo=object(),
            use_godot=False,
            renderer="qpaint",
        )
        qtbot.addWidget(win)
        win.show()
        qtbot.wait(20)

        assert win._viewport_host is not None
        assert not win._viewport_host.isHidden()
