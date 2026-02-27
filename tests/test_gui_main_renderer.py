from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget


class _FakeController(QObject):
    view_changed = pyqtSignal(object)
    messages_ready = pyqtSignal(list)
    hint_options_ready = pyqtSignal(list)
    hint_result_ready = pyqtSignal(str)
    game_completed = pyqtSignal(dict)

    def on_command(self, _command) -> None:
        pass


class _FakeBackend:
    def __init__(self) -> None:
        self.resize_calls = 0
        self.start_calls = 0

    def is_ready(self) -> bool:
        return self.start_calls > 0

    def start(self, _parent_widget) -> None:
        self.start_calls += 1

    def _handle_resize(self) -> None:
        self.resize_calls += 1


class _FakeCanvas(QWidget):
    direction_clicked = pyqtSignal(str)
    godot_process_started = pyqtSignal(int)
    facing_changed = pyqtSignal(str)

    def __init__(self, backend: _FakeBackend) -> None:
        super().__init__()
        self._backend = backend

    def update_maze(self, _snapshot) -> None:
        pass

    def highlight_player(self, _pos) -> None:
        pass

    def set_view_direction(self, _direction: str) -> None:
        pass

    def facing_direction(self) -> str:
        return "S"


def test_mainwindow_panda3d_viewport_resize_sync(qtbot, monkeypatch):
    """Panda3D renderer path must receive viewport resize events."""
    import gui_main

    # Keep this test focused on viewport wiring only.
    monkeypatch.setattr(gui_main, "FormsPanel", None)
    monkeypatch.setattr(gui_main, "PuzzleDialog", None)
    monkeypatch.setattr(gui_main, "StatusBar", None)
    monkeypatch.setattr(gui_main, "ScoreBoard", None)
    monkeypatch.setattr(gui_main, "MazeCanvas", _FakeCanvas)

    backend = _FakeBackend()

    def _fake_create_panda3d_canvas(self):
        return _FakeCanvas(backend)

    monkeypatch.setattr(gui_main.MainWindow, "_create_panda3d_canvas", _fake_create_panda3d_canvas)

    win = gui_main.MainWindow(
        _FakeController(),
        repo=object(),
        use_godot=False,
        renderer="panda3d",
    )
    qtbot.addWidget(win)
    win.show()
    qtbot.wait(20)

    host = win._viewport_host
    assert host is not None
    host.resize(host.width() + 24, host.height() + 24)
    qtbot.wait(20)

    assert backend.start_calls >= 1
    assert backend.resize_calls >= 1


def test_mainwindow_pygame_viewport_resize_sync(qtbot, monkeypatch):
    """Pygame renderer path must receive viewport resize events."""
    import gui_main

    monkeypatch.setattr(gui_main, "FormsPanel", None)
    monkeypatch.setattr(gui_main, "PuzzleDialog", None)
    monkeypatch.setattr(gui_main, "StatusBar", None)
    monkeypatch.setattr(gui_main, "ScoreBoard", None)
    monkeypatch.setattr(gui_main, "MazeCanvas", _FakeCanvas)

    backend = _FakeBackend()
    _fake_viewport = QWidget()

    def _fake_create_pygame_canvas(self):
        self._pygame_viewport = _fake_viewport
        self._pygame_embedded = True
        return _FakeCanvas(backend)

    monkeypatch.setattr(gui_main.MainWindow, "_create_pygame_canvas", _fake_create_pygame_canvas)

    win = gui_main.MainWindow(
        _FakeController(),
        repo=object(),
        use_godot=False,
        renderer="pygame",
    )
    qtbot.addWidget(win)
    win.show()
    qtbot.wait(20)

    host = win._viewport_host
    assert host is not None
    host.resize(host.width() + 24, host.height() + 24)
    qtbot.wait(20)

    assert backend.start_calls >= 1
    assert backend.resize_calls >= 1


def test_mainwindow_pygame_import_fallback_hides_empty_viewport(qtbot, monkeypatch):
    """When pygame is unavailable, the empty viewport host should be hidden."""
    import gui_main

    monkeypatch.setattr(gui_main, "FormsPanel", None)
    monkeypatch.setattr(gui_main, "PuzzleDialog", None)
    monkeypatch.setattr(gui_main, "StatusBar", None)
    monkeypatch.setattr(gui_main, "ScoreBoard", None)
    monkeypatch.setattr(gui_main, "MazeCanvas", _FakeCanvas)

    backend = _FakeBackend()

    def _fake_create_pygame_canvas(self):
        self._pygame_embedded = False
        return _FakeCanvas(backend)

    monkeypatch.setattr(gui_main.MainWindow, "_create_pygame_canvas", _fake_create_pygame_canvas)

    win = gui_main.MainWindow(
        _FakeController(),
        repo=object(),
        use_godot=False,
        renderer="pygame",
    )
    qtbot.addWidget(win)
    win.show()
    qtbot.wait(20)

    host = win._viewport_host
    assert host is not None
    assert host.isHidden()
