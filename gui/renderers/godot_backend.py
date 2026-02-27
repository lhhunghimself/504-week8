"""Godot 4 renderer backend — subprocess + WebSocket bridge.

Launches Godot as a QProcess and communicates via QWebSocketServer.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QProcess, QTimer, pyqtSignal
from PyQt6.QtCore import QObject

try:
    from PyQt6.QtWebSockets import QWebSocket, QWebSocketServer
    _HAS_WEBSOCKETS = True
except ImportError:
    _HAS_WEBSOCKETS = False

from gui.renderers.base_backend import BaseBackend

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

log = logging.getLogger(__name__)

GODOT_PROJECT_DIR = Path(__file__).resolve().parent.parent.parent / "godot_maze"
GODOT_CONNECT_TIMEOUT_MS = 5000


def _find_godot() -> str | None:
    for name in ("godot", "godot4", "godot-4", "Godot_v4"):
        path = shutil.which(name)
        if path:
            return path
    return None


class GodotBackend(BaseBackend, QObject):
    """Godot subprocess + WebSocket renderer backend."""

    process_started = pyqtSignal(int)

    def __init__(self, *, godot_parent_widget: QWidget | None = None) -> None:
        BaseBackend.__init__(self)
        QObject.__init__(self)

        self._godot_exe = _find_godot()
        self._godot_parent_widget = godot_parent_widget

        self._ws_server: QWebSocketServer | None = None
        self._ws_client: QWebSocket | None = None
        self._godot_process: QProcess | None = None
        self._ws_port: int = 0
        self._pending_messages: list[str] = []
        self._connect_timeout: QTimer | None = None
        self._is_closing = False
        self._godot_stderr_tail: list[str] = []
        self._started = False

        self._on_fallback_cb = None

    def on_fallback(self, callback) -> None:
        """Register callback for when Godot fails and falls back to 2D."""
        self._on_fallback_cb = callback

    @classmethod
    def check_availability(cls) -> str | None:
        """Return a reason string if Godot is unavailable, or None if OK."""
        if _find_godot() is None:
            return ("Godot not found on PATH — install Godot 4.2+ and ensure "
                    "'godot' is on your PATH (see README)")
        if not _HAS_WEBSOCKETS:
            return "PyQt6-WebSockets not installed (pip install PyQt6-WebSockets)"
        if not GODOT_PROJECT_DIR.is_dir():
            return f"Godot project directory not found: {GODOT_PROJECT_DIR}"
        return None

    # -- BaseBackend implementation -----------------------------------------

    def start(self, parent_widget: QWidget) -> None:
        if self._started:
            return
        self._started = True
        self._start_ws_server()

    def stop(self) -> None:
        self._is_closing = True
        if self._connect_timeout and self._connect_timeout.isActive():
            self._connect_timeout.stop()
        self._kill_godot()
        if self._ws_client:
            self._ws_client.close()
            self._ws_client = None
        if self._ws_server:
            self._ws_server.close()
            self._ws_server = None
        self._started = False
        self._is_closing = False

    def is_ready(self) -> bool:
        return self._ws_client is not None

    def send_maze_update(self, snapshot_dict: dict) -> None:
        self._send({"type": "maze_update", "snapshot": snapshot_dict})
        if self._godot_process is None and self._started:
            self._launch_godot()

    def send_highlight_player(self, row: int, col: int) -> None:
        self._send({"type": "highlight_player", "row": row, "col": col})

    def send_view_direction(self, direction: str) -> None:
        d = (direction or "").strip().upper()
        if d in ("N", "S", "E", "W"):
            self._send({"type": "set_view_direction", "value": d})

    # -- WebSocket ----------------------------------------------------------

    def _start_ws_server(self) -> None:
        self._ws_server = QWebSocketServer(
            "MazeCanvasBridge",
            QWebSocketServer.SslMode.NonSecureMode,
            self,
        )
        if self._ws_server.listen(port=0):
            self._ws_port = self._ws_server.serverPort()
            self._ws_server.newConnection.connect(self._on_connected)
            log.info("WebSocket server listening on port %d", self._ws_port)
        else:
            self._trigger_fallback("Failed to start WebSocket server")

    def _on_connected(self) -> None:
        if self._ws_server is None:
            return
        if self._connect_timeout and self._connect_timeout.isActive():
            self._connect_timeout.stop()
        self._ws_client = self._ws_server.nextPendingConnection()
        if self._ws_client:
            self._ws_client.textMessageReceived.connect(self._on_message)
            log.info("Godot connected via WebSocket")
            if self._pending_messages:
                for pending in self._pending_messages:
                    self._ws_client.sendTextMessage(pending)
                self._pending_messages.clear()

    def _on_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        msg_type = msg.get("type")
        value = msg.get("value", "")
        if msg_type == "direction" and value in ("N", "S", "E", "W"):
            self._emit_facing(value)
            self._emit_direction(value)
        elif msg_type == "facing" and value in ("N", "S", "E", "W"):
            self._emit_facing(value)

    def _send(self, msg: dict) -> None:
        text = json.dumps(msg, separators=(",", ":"))
        if self._ws_client:
            self._ws_client.sendTextMessage(text)
        else:
            self._pending_messages.append(text)

    # -- Godot process ------------------------------------------------------

    def _launch_godot(self) -> None:
        if self._godot_process is not None or not self._godot_exe or not self._started:
            return

        self._godot_process = QProcess(self)
        self._godot_process.setWorkingDirectory(str(GODOT_PROJECT_DIR))
        self._godot_process.started.connect(self._on_godot_started)
        self._godot_process.errorOccurred.connect(self._on_godot_error)
        self._godot_process.finished.connect(self._on_godot_finished)
        self._godot_process.readyReadStandardError.connect(self._on_stderr)
        self._godot_process.readyReadStandardOutput.connect(self._on_stdout)

        args = ["--path", str(GODOT_PROJECT_DIR)]
        if (
            self._godot_parent_widget is not None
            and os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11"
            and os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen"
        ):
            args.extend(["--single-window", "--display-driver", "x11",
                         "--rendering-driver", "opengl3"])
        args.extend(["--", f"--ws-port={self._ws_port}"])

        log.info("Launching Godot: %s %s", self._godot_exe, " ".join(args))
        self._godot_process.start(self._godot_exe, args)
        self._start_connect_timeout()

    def _on_godot_started(self) -> None:
        if self._godot_process is None:
            return
        self.process_started.emit(int(self._godot_process.processId()))

    def _start_connect_timeout(self) -> None:
        if self._connect_timeout is None:
            self._connect_timeout = QTimer(self)
            self._connect_timeout.setSingleShot(True)
            self._connect_timeout.timeout.connect(self._on_connect_timeout)
        self._connect_timeout.start(GODOT_CONNECT_TIMEOUT_MS)

    def _on_connect_timeout(self) -> None:
        if self._is_closing:
            return
        if self._ws_client is None:
            self._trigger_fallback(
                "Godot did not connect to bridge within 5s "
                "(check that Godot 4.2+ launches and supports WebSocketPeer)"
            )

    def _on_godot_error(self, err: QProcess.ProcessError) -> None:
        if self._is_closing:
            return
        self._trigger_fallback(f"Godot process error: {err.name}")

    def _on_godot_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._godot_process = None
        if self._is_closing:
            return
        detail = f"Godot exited (code={exit_code}, status={exit_status.name})"
        if self._godot_stderr_tail:
            detail = f"{detail} — {self._godot_stderr_tail[-1]}"
        self._trigger_fallback(detail)

    def _on_stderr(self) -> None:
        if self._godot_process is None:
            return
        chunk = bytes(self._godot_process.readAllStandardError()).decode("utf-8", errors="replace")
        if not chunk:
            return
        for line in chunk.splitlines():
            line = line.strip()
            if line:
                self._godot_stderr_tail.append(line)
        if len(self._godot_stderr_tail) > 10:
            self._godot_stderr_tail = self._godot_stderr_tail[-10:]
        log.warning("Godot stderr: %s", chunk.rstrip())

    def _on_stdout(self) -> None:
        if self._godot_process is None:
            return
        chunk = bytes(self._godot_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if chunk:
            log.info("Godot stdout: %s", chunk.rstrip())

    def _kill_godot(self) -> None:
        proc = self._godot_process
        self._godot_process = None
        if proc and proc.state() != QProcess.ProcessState.NotRunning:
            proc.terminate()
            if not proc.waitForFinished(1500):
                proc.kill()
                proc.waitForFinished(3000)

    def _trigger_fallback(self, reason: str) -> None:
        self._pending_messages.clear()
        log.warning("Godot backend: fallback — %s", reason)
        if self._connect_timeout and self._connect_timeout.isActive():
            self._connect_timeout.stop()
        if self._ws_client:
            self._ws_client.close()
            self._ws_client = None
        if self._ws_server:
            self._ws_server.close()
            self._ws_server = None
        self._kill_godot()
        self._started = False
        if self._on_fallback_cb:
            self._on_fallback_cb(reason)
