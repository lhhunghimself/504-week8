"""Abstract base class for 3D renderer backends.

Each backend is responsible for:
  - Managing its own rendering lifecycle (start/stop)
  - Accepting maze state via send_maze_update / send_highlight_player
  - Reporting user input events (direction, facing) via callbacks
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget


class BaseBackend:
    """Interface that all 3D renderer backends must implement.

    Not an ABC to avoid metaclass conflicts with QObject subclasses.
    Subclasses must override all public methods.
    """

    def __init__(self) -> None:
        self._on_direction_cb: Callable[[str], None] | None = None
        self._on_facing_cb: Callable[[str], None] | None = None

    # -- Lifecycle ----------------------------------------------------------

    def start(self, parent_widget: QWidget) -> None:
        """Initialise rendering into *parent_widget*."""
        raise NotImplementedError

    def stop(self) -> None:
        """Tear down all rendering resources."""
        raise NotImplementedError

    def is_ready(self) -> bool:
        """Return True when the backend is initialised and accepting data."""
        raise NotImplementedError

    # -- Data input ---------------------------------------------------------

    def send_maze_update(self, snapshot_dict: dict) -> None:
        """Push a full maze snapshot (as a plain dict) to the renderer."""
        raise NotImplementedError

    def send_highlight_player(self, row: int, col: int) -> None:
        """Update the player highlight position."""
        raise NotImplementedError

    def send_view_direction(self, direction: str) -> None:
        """Set the camera/view facing direction (N/S/E/W)."""
        raise NotImplementedError

    # -- Input injection (for embedded backends that can't capture OS focus) --

    def inject_key(self, panda_key: str, *, pressed: bool) -> None:
        """Inject a key press/release by name (e.g. 'w', 'arrow_left').

        Called by MazeCanvas.keyPressEvent/keyReleaseEvent to forward Qt key
        events to the embedded renderer when the renderer window cannot receive
        direct OS keyboard focus.  The default no-ops; Panda3DBackend overrides.
        """

    # -- Event callbacks ----------------------------------------------------

    def on_direction(self, callback: Callable[[str], None]) -> None:
        """Register a callback for movement direction events from the renderer."""
        self._on_direction_cb = callback

    def on_facing(self, callback: Callable[[str], None]) -> None:
        """Register a callback for facing-change events from the renderer."""
        self._on_facing_cb = callback

    def _emit_direction(self, direction: str) -> None:
        if self._on_direction_cb and direction in ("N", "S", "E", "W"):
            self._on_direction_cb(direction)

    def _emit_facing(self, direction: str) -> None:
        if self._on_facing_cb and direction in ("N", "S", "E", "W"):
            self._on_facing_cb(direction)
