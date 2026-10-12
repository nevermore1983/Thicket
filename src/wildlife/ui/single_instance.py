"""Only one WildLife window at a time: a second launch brings the first to the front."""

from __future__ import annotations

import getpass
from collections.abc import Callable

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = f"WildLife-{getpass.getuser()}"


def another_instance_is_running(ask_to_show: bool = True) -> bool:
    """If WildLife is already open, ask it to show itself (unless told not to) and return True."""
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(300):
        if ask_to_show:
            socket.write(b"show")
            socket.waitForBytesWritten(300)
        socket.disconnectFromServer()
        return True
    return False


def restart_wildlife(data_dir: str) -> bool:
    """Start a new WildLife (the caller then closes this one). True if it started."""
    import sys

    from PySide6.QtCore import QProcess

    args = ["--data-dir", data_dir, "--restarting"]
    if getattr(sys, "frozen", False):  # the packaged WildLife.exe
        return QProcess.startDetached(sys.executable, args)[0]
    return QProcess.startDetached(sys.executable, ["-m", "wildlife.app", *args])[0]


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
