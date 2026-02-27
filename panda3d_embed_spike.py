"""Panda3D-in-PyQt6 embedding feasibility spike.

Validates that Panda3D can render inside a QWidget driven by QTimer,
without owning the main loop.  Success criteria:
  1. First frame renders without manual resize.
  2. No crashes on open/close/reopen cycle (3 iterations).
  3. Qt widgets remain responsive while Panda3D renders.
  4. No OpenGL context errors in stderr.
"""
from __future__ import annotations

import sys
import logging

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


class Panda3DEmbedWidget(QWidget):
    """Host widget that creates a Panda3D window inside itself."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setMinimumSize(400, 300)

        self._base = None
        self._timer = None
        self._cube = None
        self._angle = 0.0

    def start(self) -> bool:
        """Initialise Panda3D inside this widget. Returns True on success."""
        if self._base is not None:
            return True

        try:
            from direct.showbase.ShowBase import ShowBase
            from panda3d.core import WindowProperties, loadPrcFileData

            loadPrcFileData("", "window-type none")
            loadPrcFileData("", "audio-library-name null")

            self._base = ShowBase(windowType="none")

            props = WindowProperties()
            props.setParentWindow(int(self.winId()))
            props.setSize(self.width(), self.height())
            props.setOrigin(0, 0)

            self._base.openDefaultWindow(props=props)
            log.info("Panda3D window opened inside Qt widget (size=%dx%d)", self.width(), self.height())

            self._build_scene()

            self._timer = QTimer(self)
            self._timer.timeout.connect(self._step)
            self._timer.start(16)

            return True

        except Exception:
            log.exception("Failed to initialise Panda3D")
            self._base = None
            return False

    def stop(self) -> None:
        """Tear down Panda3D cleanly."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

        if self._base is not None:
            try:
                self._base.destroy()
            except Exception:
                log.exception("Error destroying Panda3D base")
            self._base = None

        self._cube = None
        self._angle = 0.0
        log.info("Panda3D stopped")

    def _build_scene(self) -> None:
        """Create a simple spinning cube scene."""
        from panda3d.core import AmbientLight, DirectionalLight, LVector4

        cube = self._base.loader.loadModel("models/box")
        cube.reparentTo(self._base.render)
        cube.setScale(1.5)
        cube.setPos(0, 6, 0)
        self._cube = cube

        ambient = AmbientLight("ambient")
        ambient.setColor(LVector4(0.3, 0.3, 0.3, 1))
        self._base.render.setLight(self._base.render.attachNewNode(ambient))

        sun = DirectionalLight("sun")
        sun.setColor(LVector4(0.9, 0.9, 0.8, 1))
        sun_np = self._base.render.attachNewNode(sun)
        sun_np.setHpr(45, -45, 0)
        self._base.render.setLight(sun_np)

        self._base.cam.setPos(0, 0, 2)
        self._base.cam.lookAt(cube)

    def _step(self) -> None:
        """Advance one Panda3D frame."""
        if self._base is None:
            return
        try:
            self._angle += 1.0
            if self._cube is not None:
                self._cube.setH(self._angle)
            self._base.taskMgr.step()
        except Exception:
            log.exception("Panda3D step error")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._base is not None and self._base.win is not None:
            from panda3d.core import WindowProperties
            props = WindowProperties()
            props.setSize(self.width(), self.height())
            self._base.win.requestProperties(props)


class SpikeWindow(QMainWindow):
    """Main window with Panda3D embed and Qt control buttons."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Panda3D Embed Spike")
        self.resize(800, 500)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        self._panda_widget = Panda3DEmbedWidget()
        root.addWidget(self._panda_widget, stretch=3)

        sidebar = QVBoxLayout()
        root.addLayout(sidebar, stretch=1)

        self._status = QLabel("Status: idle")
        sidebar.addWidget(self._status)

        self._counter_label = QLabel("Qt counter: 0")
        sidebar.addWidget(self._counter_label)
        self._counter = 0

        btn_start = QPushButton("Start Panda3D")
        btn_start.clicked.connect(self._on_start)
        sidebar.addWidget(btn_start)

        btn_stop = QPushButton("Stop Panda3D")
        btn_stop.clicked.connect(self._on_stop)
        sidebar.addWidget(btn_stop)

        btn_cycle = QPushButton("Open/Close 3x (lifecycle test)")
        btn_cycle.clicked.connect(self._on_cycle)
        sidebar.addWidget(btn_cycle)

        btn_quit = QPushButton("Quit")
        btn_quit.clicked.connect(self.close)
        sidebar.addWidget(btn_quit)

        sidebar.addStretch()

        self._qt_timer = QTimer(self)
        self._qt_timer.timeout.connect(self._tick_counter)
        self._qt_timer.start(100)

    def _tick_counter(self) -> None:
        self._counter += 1
        self._counter_label.setText(f"Qt counter: {self._counter}")

    def _on_start(self) -> None:
        ok = self._panda_widget.start()
        self._status.setText(f"Status: {'running' if ok else 'FAILED'}")

    def _on_stop(self) -> None:
        self._panda_widget.stop()
        self._status.setText("Status: stopped")

    def _on_cycle(self) -> None:
        """Open/close Panda3D 3 times to test lifecycle robustness."""
        self._status.setText("Status: cycling...")
        QApplication.processEvents()
        for i in range(3):
            log.info("Lifecycle cycle %d/3 — start", i + 1)
            ok = self._panda_widget.start()
            if not ok:
                self._status.setText(f"Status: FAILED on cycle {i+1} start")
                return
            QApplication.processEvents()
            for _ in range(30):
                self._panda_widget._step()
                QApplication.processEvents()
            self._panda_widget.stop()
            QApplication.processEvents()
            log.info("Lifecycle cycle %d/3 — done", i + 1)
        self._status.setText("Status: 3 cycles OK")

    def closeEvent(self, event) -> None:
        self._panda_widget.stop()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    win = SpikeWindow()
    win.show()

    win._on_start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
