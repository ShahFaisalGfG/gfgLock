# single_instance.py — single-instance guard via QLocalServer / QLocalSocket

import json

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_SERVER_NAME = "gfgLock_AppServer_v3"
_CONNECT_MS = 300
_RETRY_MS = 500


class SingleInstance(QObject):
    """Routes secondary instances to the primary via a named-pipe socket."""

    filesReceived = Signal(str, list)   # (mode, paths)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server: QLocalServer | None = None

    def tryForward(self, mode: str, paths: list) -> bool:
        """Forward args to an existing primary instance. Returns True if this is a secondary."""
        try:
            if self._send(mode, paths, _CONNECT_MS):
                return True
            if self._startServer():
                return False
            # Race: another instance just won the listen — retry as client
            return self._send(mode, paths, _RETRY_MS)
        except Exception:
            return False

    def close(self) -> None:
        """Shut down the server socket on app exit."""
        try:
            if self._server:
                self._server.close()
                QLocalServer.removeServer(_SERVER_NAME)
        except Exception:
            pass

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _send(self, mode: str, paths: list, timeout_ms: int) -> bool:
        """Connect to the primary and write mode+paths as JSON. Returns True on success."""
        try:
            sock = QLocalSocket()
            sock.connectToServer(_SERVER_NAME)
            if not sock.waitForConnected(timeout_ms):
                return False
            data = json.dumps({"mode": mode, "paths": paths}) + "\n"
            sock.write(data.encode("utf-8"))
            sock.flush()
            sock.waitForBytesWritten(300)
            sock.disconnectFromServer()
            return True
        except Exception:
            return False

    def _startServer(self) -> bool:
        """Attempt to become the primary instance by starting the local server."""
        try:
            QLocalServer.removeServer(_SERVER_NAME)
            server = QLocalServer()
            if not server.listen(_SERVER_NAME):
                return False
            self._server = server
            self._server.newConnection.connect(self._onConnection)
            return True
        except Exception:
            return False

    def _onConnection(self) -> None:
        """Accept all pending connections from secondary instances."""
        try:
            while self._server and self._server.hasPendingConnections():
                sock = self._server.nextPendingConnection()
                sock.readyRead.connect(lambda s=sock: self._readMessage(s))
        except Exception:
            pass

    def _readMessage(self, sock: QLocalSocket) -> None:
        """Parse incoming JSON message and emit filesReceived."""
        try:
            raw = sock.readAll().toStdString().strip()
            payload = json.loads(raw)
            mode = payload.get("mode", "")
            paths = payload.get("paths", [])
            if mode and paths:
                self.filesReceived.emit(mode, paths)
        except Exception:
            pass
