"""Tests for the Pygame raycaster renderer backend.

Validates angle/facing conversions, input handling, callbacks, safe-before-
start behaviour, orientation correctness, and (where a display is available)
lifecycle and MazeCanvas integration.
"""
from __future__ import annotations

import math
import os

import pytest

from gui.renderers.raycaster import (
    Grid,
    angle_for_facing,
    build_grid,
    cast_ray,
    facing_for_angle,
    render_frame,
)
from gui.renderers.pygame_backend import PygameBackend


# ---------------------------------------------------------------------------
# Unit tests — no display required
# ---------------------------------------------------------------------------

class TestAngleConversions:
    def test_angle_for_facing_cardinal(self):
        assert angle_for_facing("N") == pytest.approx(math.pi / 2)
        assert angle_for_facing("E") == pytest.approx(0.0)
        assert angle_for_facing("S") == pytest.approx(-math.pi / 2)
        assert angle_for_facing("W") == pytest.approx(math.pi)

    def test_facing_for_angle_cardinal(self):
        assert facing_for_angle(0.0) == "E"
        assert facing_for_angle(math.pi / 2) == "N"
        assert facing_for_angle(math.pi) == "W"
        assert facing_for_angle(3 * math.pi / 2) == "S"

    def test_facing_for_angle_wraps(self):
        assert facing_for_angle(2 * math.pi) == "E"
        assert facing_for_angle(-math.pi / 2) == "S"

    def test_round_trip_all_cardinals(self):
        for d in ("N", "E", "S", "W"):
            assert facing_for_angle(angle_for_facing(d)) == d


class TestBackendInputHandling:
    def setup_method(self):
        self.backend = PygameBackend()
        self.directions: list[str] = []
        self.facings: list[str] = []
        self.backend.on_direction(lambda d: self.directions.append(d))
        self.backend.on_facing(lambda d: self.facings.append(d))

    def test_forward_emits_current_facing(self):
        self.backend._facing_str = "N"
        self.backend._handle_action("forward")
        assert self.directions == ["N"]

    def test_backward_emits_opposite(self):
        self.backend._facing_str = "N"
        self.backend._handle_action("backward")
        assert self.directions == ["S"]

    def test_turn_left_from_south(self):
        self.backend._player_angle = angle_for_facing("S")
        self.backend._facing_str = "S"
        self.backend._handle_action("turn_left")
        assert self.backend._facing_str == "E"
        assert "E" in self.facings

    def test_turn_right_from_south(self):
        self.backend._player_angle = angle_for_facing("S")
        self.backend._facing_str = "S"
        self.backend._handle_action("turn_right")
        assert self.backend._facing_str == "W"
        assert "W" in self.facings

    def test_full_rotation_left(self):
        self.backend._player_angle = angle_for_facing("N")
        self.backend._facing_str = "N"
        for _ in range(4):
            self.backend._handle_action("turn_left")
        assert self.backend._facing_str == "N"

    def test_full_rotation_right(self):
        self.backend._player_angle = angle_for_facing("N")
        self.backend._facing_str = "N"
        for _ in range(4):
            self.backend._handle_action("turn_right")
        assert self.backend._facing_str == "N"

    def test_movement_sequence(self):
        self.backend._player_angle = angle_for_facing("S")
        self.backend._facing_str = "S"
        self.backend._handle_action("forward")
        self.backend._handle_action("turn_left")
        self.backend._handle_action("forward")
        assert self.directions == ["S", "E"]
        assert self.facings == ["E"]


class TestBackendCallbacks:
    def test_on_direction_callback(self):
        backend = PygameBackend()
        received: list[str] = []
        backend.on_direction(lambda d: received.append(d))
        backend._emit_direction("N")
        backend._emit_direction("X")
        assert received == ["N"]

    def test_on_facing_callback(self):
        backend = PygameBackend()
        received: list[str] = []
        backend.on_facing(lambda d: received.append(d))
        backend._emit_facing("W")
        backend._emit_facing("Z")
        assert received == ["W"]


class TestBackendNotStarted:
    def test_is_ready_before_start(self):
        assert not PygameBackend().is_ready()

    def test_stop_before_start(self):
        PygameBackend().stop()

    def test_send_maze_update_before_start(self):
        b = PygameBackend()
        b.send_maze_update({"width": 3, "height": 3, "cells": []})
        assert b._grid is not None

    def test_send_highlight_before_start(self):
        PygameBackend().send_highlight_player(0, 0)

    def test_send_view_direction_before_start(self):
        b = PygameBackend()
        b.send_view_direction("N")
        assert b._facing_str == "N"

    def test_double_stop(self):
        b = PygameBackend()
        b.stop()
        b.stop()

    def test_send_maze_update_syncs_player_from_snapshot(self):
        b = PygameBackend()
        snapshot = {
            "width": 3,
            "height": 3,
            "cells": [
                {
                    "row": r,
                    "col": c,
                    "kind": "normal",
                    "visible": True,
                    "is_player": (r == 2 and c == 1),
                    "has_gate": False,
                    "solved": False,
                    "connections": [],
                }
                for r in range(3)
                for c in range(3)
            ],
        }
        b.send_maze_update(snapshot)
        assert b._player_x == pytest.approx(1.5)
        assert b._player_y == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# Orientation correctness (catches N-vs-E class of bugs)
# ---------------------------------------------------------------------------

class TestOrientationCorrectness:
    """Verify that after turns the facing string matches the expected compass."""

    @staticmethod
    def _fresh_backend(facing: str = "N") -> PygameBackend:
        b = PygameBackend()
        b._player_angle = angle_for_facing(facing)
        b._facing_str = facing
        return b

    def test_facing_after_turn_left_from_north(self):
        b = self._fresh_backend("N")
        b._handle_action("turn_left")
        assert b._facing_str == "W"

    def test_facing_after_turn_right_from_north(self):
        b = self._fresh_backend("N")
        b._handle_action("turn_right")
        assert b._facing_str == "E"

    def test_facing_after_turn_left_from_east(self):
        b = self._fresh_backend("E")
        b._handle_action("turn_left")
        assert b._facing_str == "N"

    def test_facing_after_turn_right_from_east(self):
        b = self._fresh_backend("E")
        b._handle_action("turn_right")
        assert b._facing_str == "S"

    def test_facing_after_turn_left_from_south(self):
        b = self._fresh_backend("S")
        b._handle_action("turn_left")
        assert b._facing_str == "E"

    def test_facing_after_turn_right_from_south(self):
        b = self._fresh_backend("S")
        b._handle_action("turn_right")
        assert b._facing_str == "W"

    def test_facing_after_turn_left_from_west(self):
        b = self._fresh_backend("W")
        b._handle_action("turn_left")
        assert b._facing_str == "S"

    def test_facing_after_turn_right_from_west(self):
        b = self._fresh_backend("W")
        b._handle_action("turn_right")
        assert b._facing_str == "N"

    def test_send_view_direction_sets_angle_and_string(self):
        b = PygameBackend()
        for d in ("N", "E", "S", "W"):
            b.send_view_direction(d)
            assert b._facing_str == d
            assert b._player_angle == pytest.approx(angle_for_facing(d))


# ---------------------------------------------------------------------------
# Raycaster grid / ray cast unit tests
# ---------------------------------------------------------------------------

class TestBuildGrid:
    def test_empty_snapshot(self):
        g = build_grid({"width": 0, "height": 0, "cells": []})
        assert g.width == 0 and g.height == 0

    def test_simple_3x3(self):
        cells = [
            {"row": r, "col": c, "kind": "normal", "visible": True,
             "is_player": (r == 0 and c == 0), "has_gate": False,
             "solved": False, "connections": []}
            for r in range(3) for c in range(3)
        ]
        g = build_grid({"width": 3, "height": 3, "cells": cells})
        assert g.width == 3 and g.height == 3
        cell = g.cell(0, 0)
        assert cell is not None
        assert cell.is_player is True
        assert all(cell.walls[d] for d in "NSEW")

    def test_connections_remove_walls(self):
        cells = [
            {"row": 0, "col": 0, "kind": "normal", "visible": True,
             "is_player": True, "has_gate": False, "solved": False,
             "connections": ["E", "S"]},
        ]
        g = build_grid({"width": 2, "height": 2, "cells": cells})
        c = g.cell(0, 0)
        assert c is not None
        assert c.walls["E"] is False
        assert c.walls["S"] is False
        assert c.walls["N"] is True
        assert c.walls["W"] is True


class TestCastRay:
    @staticmethod
    def _walled_grid() -> Grid:
        """1x1 grid — walls on all sides."""
        return build_grid({
            "width": 1, "height": 1,
            "cells": [
                {"row": 0, "col": 0, "kind": "normal", "visible": True,
                 "is_player": True, "has_gate": False, "solved": False,
                 "connections": []},
            ],
        })

    def test_ray_east_hits_wall(self):
        g = self._walled_grid()
        hit = cast_ray(g, 0.5, 0.5, 0.0)
        assert hit is not None
        assert hit.wall_dir == "E"
        assert hit.distance == pytest.approx(0.5, abs=0.05)
        assert 0.0 <= hit.wall_x < 1.0

    def test_ray_north_hits_wall(self):
        g = self._walled_grid()
        hit = cast_ray(g, 0.5, 0.5, math.pi / 2)
        assert hit is not None
        assert hit.wall_dir == "N"
        assert hit.distance == pytest.approx(0.5, abs=0.05)
        assert 0.0 <= hit.wall_x < 1.0

    def test_ray_west_hits_wall(self):
        g = self._walled_grid()
        hit = cast_ray(g, 0.5, 0.5, math.pi)
        assert hit is not None
        assert hit.wall_dir == "W"
        assert 0.0 <= hit.wall_x < 1.0

    def test_ray_south_hits_wall(self):
        g = self._walled_grid()
        hit = cast_ray(g, 0.5, 0.5, -math.pi / 2)
        assert hit is not None
        assert hit.wall_dir == "S"
        assert 0.0 <= hit.wall_x < 1.0

    def test_wall_x_center_hit(self):
        """A ray cast from center of a 1x1 cell should hit the wall at ~0.5."""
        g = self._walled_grid()
        hit = cast_ray(g, 0.5, 0.5, 0.0)
        assert hit is not None
        assert hit.wall_x == pytest.approx(0.5, abs=0.05)


class TestTexturedRenderFrame:
    """Verify render_frame completes without errors on the textured path."""

    @staticmethod
    def _make_surface_and_grid():
        import pygame as pg
        pg.init()
        surface = pg.Surface((160, 120))
        snapshot = {
            "width": 3, "height": 3,
            "cells": [
                {"row": r, "col": c, "kind": "normal", "visible": True,
                 "is_player": (r == 0 and c == 0), "has_gate": False,
                 "solved": False, "connections": ["E"] if c < 2 else []}
                for r in range(3) for c in range(3)
            ],
        }
        grid = build_grid(snapshot)
        return surface, grid

    def test_render_completes(self):
        surface, grid = self._make_surface_and_grid()
        render_frame(surface, grid, 0.5, 0.5, 0.0, 160, 120)

    def test_render_all_facings(self):
        """Render from each cardinal direction without error."""
        surface, grid = self._make_surface_and_grid()
        for facing in ("N", "E", "S", "W"):
            angle = angle_for_facing(facing)
            render_frame(surface, grid, 0.5, 0.5, angle, 160, 120)

    def test_render_gate_and_exit_cells(self):
        """Render a grid containing gate and exit cells for texture selection."""
        import pygame as pg
        pg.init()
        surface = pg.Surface((160, 120))
        snapshot = {
            "width": 2, "height": 2,
            "cells": [
                {"row": 0, "col": 0, "kind": "start", "visible": True,
                 "is_player": True, "has_gate": False, "solved": False,
                 "connections": ["E"]},
                {"row": 0, "col": 1, "kind": "normal", "visible": True,
                 "is_player": False, "has_gate": True, "solved": False,
                 "connections": ["W"]},
                {"row": 1, "col": 0, "kind": "normal", "visible": True,
                 "is_player": False, "has_gate": True, "solved": True,
                 "connections": ["E"]},
                {"row": 1, "col": 1, "kind": "exit", "visible": True,
                 "is_player": False, "has_gate": False, "solved": False,
                 "connections": ["W"]},
            ],
        }
        grid = build_grid(snapshot)
        render_frame(surface, grid, 0.5, 0.5, 0.0, 160, 120)

    def test_render_tiny_surface(self):
        """Render to a very small surface without crashing."""
        import pygame as pg
        pg.init()
        surface = pg.Surface((4, 4))
        snapshot = {
            "width": 1, "height": 1,
            "cells": [{"row": 0, "col": 0, "kind": "normal", "visible": True,
                        "is_player": True, "has_gate": False, "solved": False,
                        "connections": []}],
        }
        grid = build_grid(snapshot)
        render_frame(surface, grid, 0.5, 0.5, 0.0, 4, 4)


# ---------------------------------------------------------------------------
# Display-required tests
# ---------------------------------------------------------------------------

_has_display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
_skip_no_display = pytest.mark.skipif(not _has_display, reason="No display available")


@_skip_no_display
class TestBackendLifecycle:
    @pytest.fixture(autouse=True)
    def _qt_app(self, qtbot):
        self.qtbot = qtbot

    def _make_viewport(self):
        backend = PygameBackend()
        from gui.renderers.pygame_backend import PygameViewport
        vp = PygameViewport(backend)
        vp.setMinimumSize(200, 150)
        self.qtbot.addWidget(vp)
        vp.show()
        return backend, vp

    def test_start_stop(self):
        backend, vp = self._make_viewport()
        backend.start(vp)
        assert backend.is_ready()
        backend.stop()
        assert not backend.is_ready()

    def test_double_stop(self):
        backend, vp = self._make_viewport()
        backend.start(vp)
        backend.stop()
        backend.stop()

    def test_send_maze_update_renders(self):
        backend, vp = self._make_viewport()
        backend.start(vp)
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
        assert backend._grid is not None
        assert backend._grid.width == 3
        backend.stop()


@_skip_no_display
class TestMazeCanvasWithPygame:
    @pytest.fixture(autouse=True)
    def _qt_app(self, qtbot):
        self.qtbot = qtbot

    def test_canvas_with_backend(self):
        from gui.maze_canvas import MazeCanvas
        from gui.renderers.pygame_backend import PygameViewport
        from main import CellView, MazeSnapshot

        backend = PygameBackend()
        vp = PygameViewport(backend)
        vp.setMinimumSize(200, 150)
        self.qtbot.addWidget(vp)
        vp.show()

        canvas = MazeCanvas(use_godot=False, backend=backend)
        self.qtbot.addWidget(canvas)
        backend.start(vp)

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
                         is_player=False, has_gate=False, solved=False),
                CellView(row=1, col=0, kind="normal", visible=True,
                         is_player=False, has_gate=False, solved=False,
                         connections=["N"]),
                CellView(row=1, col=1, kind="normal", visible=False,
                         is_player=False, has_gate=True, solved=False),
                CellView(row=1, col=2, kind="normal", visible=False,
                         is_player=False, has_gate=False, solved=False),
                CellView(row=2, col=0, kind="normal", visible=False,
                         is_player=False, has_gate=False, solved=False),
                CellView(row=2, col=1, kind="normal", visible=False,
                         is_player=False, has_gate=False, solved=False),
                CellView(row=2, col=2, kind="exit", visible=False,
                         is_player=False, has_gate=False, solved=False),
            ],
        )
        canvas.update_maze(snapshot)
        assert canvas.cell_count() == 9
        assert canvas.has_player_indicator(0, 0)
        assert backend.is_ready()
        backend.stop()
