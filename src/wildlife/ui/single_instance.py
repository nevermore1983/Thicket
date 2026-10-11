"""Only one WildLife window at a time: a second launch brings the first to the front."""

from __future__ import annotations

import getpass
from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = f"WildLife-{getpass.getuser()}"


def another_instance_is_running() -> bool:
    """If WildLife is already open, ask it to show itself and return True."""
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(300):
        socket.write(b"show")
        socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True
    return False


class InstanceServer(QObject):
    """Listens for later launches and calls `on_activate` when one happens."""

    def __init__(self, on_activate: Callable[[], None], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server = QLocalServer(self)
        QLocalServer.removeServer(SERVER_NAME)  # clean up after a crash
        self._server.listen(SERVER_NAME)
        self._server.newConnection.connect(
            lambda: (self._server.nextPendingConnection(), on_activate())
        )
