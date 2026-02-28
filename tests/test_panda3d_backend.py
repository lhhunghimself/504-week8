"""Tests for the Panda3D in-process renderer backend.

These tests validate backend lifecycle, input handling, and integration
with MazeCanvas.  Tests that require a display are skipped when running
headless.
"""
from __future__ import annotations

import os
import pytest

from gui.renderers.panda3d_backend import (
    Panda3DBackend,
    _facing_for_heading,
    _heading_for_facing,
)


# ---------------------------------------------------------------------------
# Unit tests (no display required)
# ---------------------------------------------------------------------------

class TestHeadingConversions:
    def test_heading_for_facing_cardinal(self):
        assert _heading_for_facing("N") == 0.0
        assert _heading_for_facing("E") == 270.0
        assert _heading_for_facing("S") == 180.0
        assert _heading_for_facing("W") == 90.0

    def test_facing_for_heading_cardinal(self):
        assert _facing_for_heading(0.0) == "N"
        assert _facing_for_heading(90.0) == "W"
        assert _facing_for_heading(180.0) == "S"
        assert _facing_for_heading(270.0) == "E"

    def test_facing_for_heading_wraps(self):
        assert _facing_for_heading(360.0) == "N"
        assert _facing_for_heading(-90.0) == "E"
        assert _facing_for_heading(450.0) == "W"


class TestBackendInputHandling:
    """Test keyboard input mapping without a display."""

    def setup_method(self):
        self.backend = Panda3DBackend()
        self.directions: list[str] = []
        self.facings: list[str] = []
        self.backend.on_direction(lambda d: self.directions.append(d))
        self.backend.on_facing(lambda d: self.facings.append(d))

    def test_forward_emits_current_facing(self):
        self.backend._facing_str = "N"
        self.backend._handle_key_press("forward")
        assert self.directions == ["N"]

    def test_backward_emits_opposite(self):
        self.backend._facing_str = "N"
        self.backend._handle_key_press("backward")
        assert self.directions == ["S"]

    def test_turn_left_from_south(self):
        self.backend._facing_h = 180.0
        self.backend._facing_str = "S"
        self.backend._handle_key_press("turn_left")
        assert self.backend._facing_str == "E"
        assert "E" in self.facings

    def test_turn_right_from_south(self):
        self.backend._facing_h = 180.0
        self.backend._facing_str = "S"
        self.backend._handle_key_press("turn_right")
        assert self.backend._facing_str == "W"
        assert "W" in self.facings

    def test_arrow_key_turn_aliases(self):
        self.backend._facing_h = 180.0
        self.backend._facing_str = "S"
        # Same internal actions used by arrow-left / arrow-right bindings.
        self.backend._handle_key_press("turn_left")
        assert self.backend._facing_str == "E"
        self.backend._handle_key_press("turn_right")
        assert self.backend._facing_str == "S"

    def test_full_rotation(self):
        """Four right turns returns to original facing."""
        self.backend._facing_h = 0.0
        self.backend._facing_str = "N"
        for _ in range(4):
            self.backend._handle_key_press("turn_right")
        assert self.backend._facing_str == "N"

    def test_movement_sequence(self):
        self.backend._facing_h = 180.0
        self.backend._facing_str = "S"
        self.backend._handle_key_press("forward")
        self.backend._handle_key_press("turn_left")
        self.backend._handle_key_press("forward")
        assert self.directions == ["S", "E"]
        assert self.facings == ["E"]


class TestBackendCallbacks:
    def test_on_direction_callback(self):
        backend = Panda3DBackend()
        received = []
        backend.on_direction(lambda d: received.append(d))
        backend._emit_direction("N")
        backend._emit_direction("X")  # invalid, should be ignored
        assert received == ["N"]

    def test_on_facing_callback(self):
        backend = Panda3DBackend()
        received = []
        backend.on_facing(lambda d: received.append(d))
        backend._emit_facing("W")
        backend._emit_facing("Z")  # invalid
        assert received == ["W"]


class TestBackendNotStarted:
    """Backend methods should be safe to call before start()."""

    def test_is_ready_before_start(self):
        backend = Panda3DBackend()
        assert not backend.is_ready()

    def test_stop_before_start(self):
        backend = Panda3DBackend()
        backend.stop()

    def test_send_maze_update_before_start(self):
        backend = Panda3DBackend()
        backend.send_maze_update({"width": 3, "height": 3, "cells": []})

    def test_send_highlight_before_start(self):
        backend = Panda3DBackend()
        backend.send_highlight_player(0, 0)

    def test_send_view_direction_before_start(self):
        backend = Panda3DBackend()
        backend.send_view_direction("N")


# ---------------------------------------------------------------------------
# Display-required tests
# ---------------------------------------------------------------------------

_has_display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
_skip_no_display = pytest.mark.skipif(not _has_display, reason="No display available")


@_skip_no_display
class TestBackendLifecycle:
    """Tests that require initialising Panda3D (need a display)."""

    @pytest.fixture(autouse=True)
    def _qt_app(self, qtbot):
        self.qtbot = qtbot

    def _make_host(self):
        from PyQt6.QtWidgets import QWidget
        from PyQt6.QtCore import Qt
        host = QWidget()
        host.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        host.setMinimumSize(400, 300)
        self.qtbot.addWidget(host)
        host.show()
        return host

    def test_start_stop(self):
        host = self._make_host()
        backend = Panda3DBackend()
        backend.start(host)
        assert backend.is_ready()
        backend.stop()
        assert not backend.is_ready()

    def test_start_stop_restart(self):
        """Open/close/reopen cycle should not crash."""
        host = self._make_host()
        backend = Panda3DBackend()
        for _ in range(3):
            backend.start(host)
            assert backend.is_ready()
            backend.stop()
            assert not backend.is_ready()

    def test_send_snapshot_renders(self):
        host = self._make_host()
        backend = Panda3DBackend()
        backend.start(host)
        snapshot = {
            "width": 3, "height": 3,
            "cells": [
                {"row": r, "col": c, "kind": "normal", "visible": True,
                 "is_player": (r == 0 and c == 0), "has_gate": False,
                 "solved": False, "connections": []}
                for r in range(3) for c in range(3)
            ],
        }
        backend.send_maze_update(snapshot)
        assert backend._maze_root is not None
        backend.stop()

    def test_double_stop_is_safe(self):
        host = self._make_host()
        backend = Panda3DBackend()
        backend.start(host)
        backend.stop()
        backend.stop()


@_skip_no_display
class TestMazeCanvasWithPanda3D:
    """Integration: MazeCanvas with a Panda3D backend."""

    @pytest.fixture(autouse=True)
    def _qt_app(self, qtbot):
        self.qtbot = qtbot

    def test_canvas_with_backend(self):
        from PyQt6.QtWidgets import QWidget
        from PyQt6.QtCore import Qt
        from gui.maze_canvas import MazeCanvas
        from main import MazeSnapshot, CellView

        host = QWidget()
        host.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        host.setMinimumSize(400, 300)
        self.qtbot.addWidget(host)
        host.show()

        backend = Panda3DBackend()
        canvas = MazeCanvas(use_godot=False, backend=backend)
        self.qtbot.addWidget(canvas)
        backend.start(host)

        snapshot = MazeSnapshot(
            width=3, height=3,
            cells=[
                CellView(row=0, col=0, kind="start", visible=True,
                         is_player=True, has_gate=False, solved=False,
                         connections=["E", "S"]),
                CellView(row=0, col=1, kind="normal", visible=True,
                         is_player=False, has_gate=False, solved=False,
                         connections=["W"]),
                CellView(row=0, col=2, kind="normal", visible=False,
                         is_player=False, has_gate=False, solved=False,
                         connections=[]),
                CellView(row=1, col=0, kind="normal", visible=True,
                         is_player=False, has_gate=False, solved=False,
                         connections=["N"]),
                CellView(row=1, col=1, kind="normal", visible=False,
                         is_player=False, has_gate=True, solved=False,
                         connections=[]),
                CellView(row=1, col=2, kind="normal", visible=False,
                         is_player=False, has_gate=False, solved=False,
                         connections=[]),
                CellView(row=2, col=0, kind="normal", visible=False,
                         is_player=False, has_gate=False, solved=False,
                         connections=[]),
                CellView(row=2, col=1, kind="normal", visible=False,
                         is_player=False, has_gate=False, solved=False,
                         connections=[]),
                CellView(row=2, col=2, kind="exit", visible=False,
                         is_player=False, has_gate=False, solved=False,
                         connections=[]),
            ],
        )
        canvas.update_maze(snapshot)
        assert canvas.cell_count() == 9
        assert canvas.has_player_indicator(0, 0)
        assert backend.is_ready()

        backend.stop()
