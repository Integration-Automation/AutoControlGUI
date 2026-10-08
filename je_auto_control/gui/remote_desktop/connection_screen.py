"""Quick Connect — single-screen AnyDesk-style entry for Remote Desktop.

The Quick Connect surface is what an operator sees first when they open
the Remote Desktop tab. It replaces the per-transport sub-tabs as the
default landing view; everything else (manual SDP, WSS, custom codecs,
TLS cert pinning) is one click away in the unchanged Advanced sub-tabs.

Design:
  * Left half — 'This machine': huge Host ID + token + Start/Stop.
  * Right half — 'Connect to': ``host:port`` input + Connect + Recent.
  * Status badges on both halves; popup viewer window on connect.
  * The Recent list and Wake-on-LAN live in ``connection_recent``.

Transport for the viewer side defaults to direct TCP (no extras needed).
Operators who want WebRTC signaling, WSS, or manual SDP exchange go to
the Advanced sub-tabs.
"""
import functools
import secrets
import threading
from pathlib import Path
from typing import Any, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._dispose import release_resources
from je_auto_control.gui._weak_call import WeakCall
from je_auto_control.gui.remote_desktop._connect_task import connect_viewer
from je_auto_control.gui.remote_desktop.connection_recent import _RecentConnectionsMixin
from je_auto_control.gui.remote_desktop._helpers import (
    _StatusBadge, _build_verifying_client_context, _t, displaced_notifier,
    wire_remote_input,
)
from je_auto_control.gui.remote_desktop.remote_screen_window import (
    RemoteScreenWindow,
)
from je_auto_control.gui._tab_task import TabTask
from je_auto_control.gui.task_controller import TaskHandle
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.remote_desktop import (
    PendingViewer, RemoteDesktopHost, RemoteDesktopViewer,
    WebSocketDesktopViewer,
)
from je_auto_control.utils.remote_desktop.address_book import (
    default_address_book,
)
from je_auto_control.utils.remote_desktop.connect_coordinator import (
    ConnectTarget, UnresolvableTargetError, parse_target,
)
from je_auto_control.utils.remote_desktop.host_id import format_host_id
from je_auto_control.utils.remote_desktop.registry import (
    SLOT_HOST, SLOT_VIEWER, SLOT_WS_VIEWER, new_owner, registry,
)

_HOST_ID_CSS = (
    "font-family: 'Consolas', 'Menlo', 'Courier New', monospace; "
    "font-size: 40pt; font-weight: bold; color: #2070d0; "
    "letter-spacing: 4px;"
)
_BIG_INPUT_CSS = (
    "font-family: 'Consolas', 'Menlo', 'Courier New', monospace; "
    "font-size: 22pt; padding: 8px; letter-spacing: 2px;"
)
_PRIMARY_BTN_CSS = (
    "font-size: 14pt; font-weight: bold; padding: 12px 28px;"
)
# Auto-reject if the operator does not answer the approval dialog in time.
# 60 s matches the auth timeout — anything longer and the viewer's socket
# is already gone.
_APPROVAL_TIMEOUT_S = 60.0


class _ApprovalRequest:
    """Threading-safe request envelope passed from host thread to GUI.

    The host's accept thread blocks on :attr:`event` while the GUI
    thread shows a modal "Allow / View only / Deny" dialog and writes
    ``decision``. Falls back to deny if the operator never answers.
    """

    __slots__ = ("pending", "event", "decision")

    def __init__(self, pending: PendingViewer) -> None:
        self.pending = pending
        self.event = threading.Event()
        # One of "full", "view_only", "denied".
        self.decision: str = "denied"


class QuickConnectScreen(_RecentConnectionsMixin, TranslatableMixin, QWidget):
    """AnyDesk-style single-screen entry point for Remote Desktop."""

    _STATUS_INTERVAL_MS = 1000

    # Emitted when the operator types a 9-digit Host ID — the parent tab
    # switches to the WebRTC viewer sub-tab and pre-fills the fields so
    # the dense signaling flow stays in the panel that owns it.
    webrtc_handoff_requested = Signal(str, str)

    # Emitted when the host operator clicks "Publish via signaling" so
    # viewers can reach this machine by 9-digit ID. Payload: (token,
    # host_id). The parent tab switches to the WebRTC Host sub-tab and
    # pre-fills the fields so the operator only needs to click Publish.
    webrtc_host_handoff_requested = Signal(str, str)

    # Bridges host-thread approval requests over to the GUI thread. The
    # payload is the in-flight :class:`_ApprovalRequest` whose ``event``
    # the GUI sets after the operator clicks Allow / Deny.
    _approval_requested = Signal(object)

    # The viewer calls its callbacks on its receiver thread; these carry
    # them to the GUI thread. They were passed straight in, so every frame
    # repainted, and a dropped connection opened a QMessageBox, off the GUI
    # thread.
    _frame_arrived = Signal(object)
    _error_arrived = Signal(str)
    _cursor_moved = Signal(int, int)
    # Another owner took one of this screen's registry slots.
    _displaced = Signal(str, str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._owner = new_owner("quick-connect")
        self._displaced.connect(self._on_displaced)
        self._host_id_label = QLabel("---")
        self._host_id_label.setStyleSheet(_HOST_ID_CSS)
        self._host_id_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._host_badge = _StatusBadge()
        self._viewer_badge = _StatusBadge()
        self._host_token = QLineEdit()
        self._host_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._connect_target = QLineEdit()
        self._connect_target.setStyleSheet(_BIG_INPUT_CSS)
        self._connect_target.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._connect_token = QLineEdit()
        self._connect_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._recent = QListWidget()
        self._recent.itemActivated.connect(self._on_recent_activated)
        # Phase 6.1: right-click a recent entry → "Wake host" via
        # build_magic_packet / send_magic_packet (the MAC is stored in
        # AddressBook when the operator saved it for a previous session).
        self._recent.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._recent.customContextMenuRequested.connect(self._on_recent_menu)
        self._start_btn: Optional[QPushButton] = None
        self._stop_btn: Optional[QPushButton] = None
        self._connect_btn: Optional[QPushButton] = None
        self._disconnect_btn: Optional[QPushButton] = None
        self._screen_window: Optional[RemoteScreenWindow] = None
        # Phase 2.3 motion-dedup interaction: a frame can arrive before
        # the popup window is open, so we cache the most recent payload
        # and replay it the moment the window is created.
        self._pending_frame: Optional[bytes] = None
        self._connect_task: Optional[TaskHandle] = None    # the connect in progress, off-thread
        self._uploads = TabTask(self)                      # dropped files going to the host, off-thread
        self._uploads.error.connect(self._on_upload_failed)
        self._uploads.finished.connect(self._refresh_status)
        self._book = default_address_book()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(self._STATUS_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._refresh_status)
        # ``Qt.QueuedConnection`` so the slot is invoked on the GUI thread
        # even though the signal is emitted from the host's accept thread.
        self._approval_requested.connect(
            self._show_approval_dialog, Qt.ConnectionType.QueuedConnection,
        )
        queued = Qt.ConnectionType.QueuedConnection
        self._frame_arrived.connect(self._on_frame, queued)
        self._error_arrived.connect(self._on_error, queued)
        self._cursor_moved.connect(self._on_remote_cursor, queued)
        self._build_layout()
        self._apply_placeholders()
        self._refresh_recent()
        self._refresh_status()
        self._refresh_timer.start()

    def dispose(self) -> None:
        """Release what the screen holds beyond its widgets: its timer, a connect or upload still out, its window.

        Called through ``RemoteDesktopTab.dispose()``; safe to call twice. The
        host this screen started and the session it opened are deliberately
        left running: they belong to the registry, where scripts
        (``AC_remote_*``) and the other panels still see them and can stop
        them. A connect that has not answered is cancelled, and the viewer it
        may still produce is disconnected.
        """
        release_resources(self, self._cancel_pending_connect, self._close_screen_window)

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_placeholders()
        self._refresh_status()

    def _apply_placeholders(self) -> None:
        self._host_token.setPlaceholderText(_t("rd_quick_token_ph"))
        self._connect_target.setPlaceholderText(_t("rd_quick_target_ph"))
        self._connect_token.setPlaceholderText(_t("rd_quick_token_ph"))

    # --- layout -------------------------------------------------------

    def _build_layout(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)
        root.addWidget(self._build_host_section(), stretch=1)
        root.addWidget(self._build_viewer_section(), stretch=1)

    def _build_host_section(self) -> QWidget:
        group = QGroupBox()
        self._tr(group, "rd_quick_this_machine", setter="setTitle")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        layout.addWidget(self._tr(QLabel(), "rd_quick_your_id"))
        layout.addWidget(self._host_id_label)

        copy_row = QHBoxLayout()
        copy_btn = self._tr(QPushButton(), "rd_quick_copy_id")
        copy_btn.clicked.connect(self._copy_host_id)
        copy_row.addStretch()
        copy_row.addWidget(copy_btn)
        copy_row.addStretch()
        layout.addLayout(copy_row)

        layout.addWidget(self._tr(QLabel(), "rd_quick_host_token"))
        token_row = QHBoxLayout()
        token_row.addWidget(self._host_token, stretch=1)
        gen_btn = self._tr(QPushButton(), "rd_quick_generate")
        gen_btn.clicked.connect(self._generate_token)
        token_row.addWidget(gen_btn)
        layout.addLayout(token_row)

        layout.addWidget(self._host_badge)

        btn_row = QHBoxLayout()
        self._start_btn = self._tr(QPushButton(), "rd_quick_start_host")
        self._start_btn.setStyleSheet(_PRIMARY_BTN_CSS)
        self._start_btn.clicked.connect(self._start_hosting)
        self._stop_btn = self._tr(QPushButton(), "rd_quick_stop_host")
        self._stop_btn.clicked.connect(self._stop_hosting)
        btn_row.addWidget(self._start_btn, stretch=2)
        btn_row.addWidget(self._stop_btn, stretch=1)
        layout.addLayout(btn_row)

        # Optional second action: hand off to the Advanced WebRTC Host
        # sub-tab so viewers can reach this machine by 9-digit ID via
        # the signaling server.
        self._publish_btn = self._tr(
            QPushButton(), "rd_quick_publish_signaling",
        )
        self._publish_btn.clicked.connect(self._on_publish_via_signaling)
        layout.addWidget(self._publish_btn)

        layout.addStretch(1)
        return group

    def _build_viewer_section(self) -> QWidget:
        group = QGroupBox()
        self._tr(group, "rd_quick_remote_machine", setter="setTitle")
        layout = QVBoxLayout(group)
        layout.setSpacing(10)

        layout.addWidget(self._tr(QLabel(), "rd_quick_target_label"))
        layout.addWidget(self._connect_target)

        layout.addWidget(self._tr(QLabel(), "rd_quick_viewer_token"))
        layout.addWidget(self._connect_token)

        layout.addWidget(self._viewer_badge)

        btn_row = QHBoxLayout()
        self._connect_btn = self._tr(QPushButton(), "rd_quick_connect_btn")
        self._connect_btn.setStyleSheet(_PRIMARY_BTN_CSS)
        self._connect_btn.clicked.connect(self._connect)
        self._disconnect_btn = self._tr(
            QPushButton(), "rd_quick_disconnect_btn",
        )
        self._disconnect_btn.clicked.connect(self._disconnect)
        btn_row.addWidget(self._connect_btn, stretch=2)
        btn_row.addWidget(self._disconnect_btn, stretch=1)
        layout.addLayout(btn_row)

        layout.addWidget(self._build_recent_box(), stretch=1)
        return group

    def _build_recent_box(self) -> QWidget:
        box = QGroupBox()
        self._tr(box, "rd_quick_recent", setter="setTitle")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 14, 8, 8)
        layout.addWidget(self._recent)
        return box

    # --- hosting ------------------------------------------------------

    def _generate_token(self) -> None:
        self._host_token.setText(secrets.token_urlsafe(24))

    def _start_hosting(self) -> None:
        token = self._host_token.text().strip()
        if not token:
            self._generate_token()
            token = self._host_token.text().strip()
        registry.evict(SLOT_HOST, by=self._owner)
        try:
            host = RemoteDesktopHost(
                token=token, bind="127.0.0.1", port=0,
                fps=10.0, quality=70,
                on_pending_viewer=self._host_approval_callback,
            )
            host.start()
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, _t("rd_quick_start_host"), str(error))
            return
        registry.adopt(SLOT_HOST, host, self._owner, displaced_notifier(self))
        self._refresh_status()

    def _host_approval_callback(self, pending: PendingViewer):
        """Bridge incoming viewers to a GUI Allow/View-only/Deny dialog.

        Runs on the host's accept thread — we ship the request over to
        the GUI thread via the queued ``_approval_requested`` signal,
        then block here until the operator clicks (or the timeout
        fires, in which case we deny).
        """
        request = _ApprovalRequest(pending)
        self._approval_requested.emit(request)
        if not request.event.wait(timeout=_APPROVAL_TIMEOUT_S):
            return False
        return request.decision

    def _show_approval_dialog(self, request: _ApprovalRequest) -> None:
        """GUI thread: ask the operator how to admit ``request.pending``."""
        try:
            address = ":".join(str(part) for part in request.pending.address)
            transport = request.pending.transport.upper()
            text = (
                _t("rd_quick_approval_message")
                .replace("{address}", address or "(unknown)")
                .replace("{transport}", transport)
            )
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle(_t("rd_quick_approval_title"))
            box.setText(text)
            allow_btn = box.addButton(
                _t("rd_quick_approval_allow"),
                QMessageBox.ButtonRole.AcceptRole,
            )
            view_only_btn = box.addButton(
                _t("rd_quick_approval_view_only"),
                QMessageBox.ButtonRole.ActionRole,
            )
            box.addButton(
                _t("rd_quick_approval_deny"),
                QMessageBox.ButtonRole.RejectRole,
            )
            box.setDefaultButton(allow_btn)
            # The host stops waiting after the timeout and denies; the box
            # stayed up, and an Allow clicked after that admitted nobody.
            QTimer.singleShot(int(_APPROVAL_TIMEOUT_S * 1000), box, box.reject)
            box.exec()
            clicked = box.clickedButton()
            if clicked is allow_btn:
                request.decision = "full"
            elif clicked is view_only_btn:
                request.decision = "view_only"
            else:
                request.decision = "denied"
        finally:
            # Always wake the host thread, even if the dialog blew up,
            # so the connection does not hang for the full timeout.
            request.event.set()

    def _stop_hosting(self) -> None:
        # Stops the host the badge shows, whoever started it; see _HostPanel._stop.
        try:
            registry.evict(SLOT_HOST, by=self._owner)
        except (OSError, RuntimeError) as error:
            QMessageBox.warning(self, _t("rd_quick_stop_host"), str(error))
            return
        self._refresh_status()

    def _copy_host_id(self) -> None:
        host = registry.host
        if host is None:
            return
        QGuiApplication.clipboard().setText(format_host_id(host.host_id))

    def _on_publish_via_signaling(self) -> None:
        """Hand off to the Advanced WebRTC Host tab with token prefilled."""
        token = self._host_token.text().strip()
        host = registry.host
        host_id = host.host_id if host is not None else ""
        self.webrtc_host_handoff_requested.emit(token, host_id)

    # --- connecting ---------------------------------------------------

    def _connect(self) -> None:
        text = self._connect_target.text().strip()
        token = self._connect_token.text().strip()
        if not text or not token:
            QMessageBox.warning(
                self, _t("rd_quick_connect_btn"),
                _t("rd_quick_required_fields"),
            )
            return
        try:
            target = parse_target(text)
        except UnresolvableTargetError as error:
            # Surface the parser error verbatim because it already
            # tells the user *which* of host / port / format is wrong.
            QMessageBox.warning(
                self, _t("rd_quick_connect_btn"),
                _t("rd_quick_bad_target") + f"\n\n{error}",
            )
            return
        self._dispatch_target(target, token)

    def _dispatch_target(self, target: ConnectTarget, token: str) -> None:
        if target.kind == "webrtc_id":
            self._handoff_to_webrtc(target.host_id or "", token)
            return
        if target.kind == "tcp":
            self._do_tcp_connect(
                target.host or "", target.port or 0, token,
            )
            return
        if target.kind in ("ws", "wss"):
            self._do_ws_connect(target, token)
            return
        # parse_target should never produce an unknown kind, but stay
        # explicit rather than silently dropping the click.
        QMessageBox.warning(
            self, _t("rd_quick_connect_btn"), _t("rd_quick_bad_target"),
        )

    def _take_slot(self, slot: str) -> None:
        """Clear ``slot`` for a new session and end this screen's other one."""
        other = SLOT_WS_VIEWER if slot == SLOT_VIEWER else SLOT_VIEWER
        registry.release(other, self._owner)
        registry.evict(slot, by=self._owner)

    def _own_viewer(self):
        """The viewer this screen opened, or None once it is gone or replaced."""
        return (registry.owned(SLOT_VIEWER, self._owner)
                or registry.owned(SLOT_WS_VIEWER, self._owner))

    def _on_displaced(self, slot: str, _by: str) -> None:
        """GUI thread: another panel or a script took one of this screen's slots."""
        if slot != SLOT_HOST and self._own_viewer() is None:
            self._pending_frame = None
            self._close_screen_window()
        self._refresh_status()

    def _viewer_callbacks(self) -> dict:
        return {"on_frame": self._frame_arrived.emit,
                "on_error": lambda exc: self._error_arrived.emit(str(exc)),
                "on_cursor": self._cursor_moved.emit}

    def _begin_connect(self, slot: str, build, on_live) -> None:
        """Take ``slot``, build the viewer, and connect it off the GUI thread (see ``_connect_task``).

        ``on_live`` is a method of this screen or a partial of one; it is held weakly.
        """
        self._cancel_pending_connect()
        self._take_slot(slot)
        try:
            viewer = build()
        except (OSError, RuntimeError, ValueError, AutoControlException) as error:
            self._on_connect_failed(error)
            return
        self._connect_task = connect_viewer(
            self, viewer, on_connected=functools.partial(self._on_viewer_live, slot, WeakCall(on_live)),
            on_failed=self._on_connect_failed)
        self._connect_task.finished.connect(self._on_connect_finished)
        self._refresh_status()

    def _on_viewer_live(self, slot: str, on_live: WeakCall, live_viewer) -> None:
        """GUI thread: the connect succeeded; register the viewer and show it."""
        registry.adopt(slot, live_viewer, self._owner, displaced_notifier(self))
        on_live()

    def _cancel_pending_connect(self) -> None:
        task, self._connect_task = self._connect_task, None
        if task is not None:
            task.cancel()

    def _on_connect_finished(self) -> None:
        if self.sender() is self._connect_task:
            self._connect_task = None
        self._refresh_status()

    def _on_connect_failed(self, error: Exception) -> None:
        # Any error: a host such as "a..b" fails IDNA encoding with UnicodeError.
        QMessageBox.warning(self, _t("rd_quick_connect_btn"), str(error))

    def _do_tcp_connect(self, host: str, port: int, token: str) -> None:
        self._begin_connect(SLOT_VIEWER, lambda: RemoteDesktopViewer(
            host=host, port=port, token=token, **self._viewer_callbacks()),
            functools.partial(self._tcp_live, host, port))

    def _tcp_live(self, host: str, port: int) -> None:
        self._remember_tcp(host, port)
        self._open_screen_window(f"{host}:{port}")

    def _ws_live(self, base: str, path: str) -> None:
        self._remember_url(f"{base}{path}")
        self._open_screen_window(base)

    def _do_ws_connect(self, target: ConnectTarget, token: str) -> None:
        host, port, path = target.host or "", target.port or 0, target.path or "/"
        scheme = "wss" if target.kind == "wss" else "ws"
        # wss:// was dialled as plain ws://: the session went unencrypted to
        # a host the operator took for TLS, and a real TLS host was unreachable.
        ssl_context = _build_verifying_client_context() if scheme == "wss" else None
        self._begin_connect(SLOT_WS_VIEWER, lambda: WebSocketDesktopViewer(
            host=host, port=port, token=token, path=path, ssl_context=ssl_context,
            **self._viewer_callbacks()), functools.partial(self._ws_live, f"{scheme}://{host}:{port}", path))

    def _on_remote_cursor(self, x: int, y: int) -> None:
        """Cursor update, delivered on the GUI thread by ``_cursor_moved``."""
        window = self._screen_window
        if window is None:
            return
        try:
            window.display.set_remote_cursor(x, y)
        except RuntimeError:
            # Window was destroyed between the null check and the call.
            pass

    def _handoff_to_webrtc(self, host_id: str, token: str) -> None:
        """Emit the signal so the parent tab can switch + prefill."""
        self.webrtc_handoff_requested.emit(host_id, token)

    def _disconnect(self) -> None:
        # Either transport, and only a session this screen opened.
        self._cancel_pending_connect()
        self._uploads.stop()    # its socket is about to close; the failure is not news
        registry.release(SLOT_VIEWER, self._owner)
        registry.release(SLOT_WS_VIEWER, self._owner)
        self._close_screen_window()
        self._refresh_status()

    # --- frame plumbing ----------------------------------------------

    def _on_frame(self, payload: bytes) -> None:
        # Cache the latest payload so a frame that lands before the
        # popup window is open can be replayed by _open_screen_window.
        self._pending_frame = payload
        window = self._screen_window
        if window is None:
            return
        image = QImage.fromData(payload, "JPEG")  # type: ignore[arg-type]  # reason: the stub says bytes; PySide6 raises ValueError for bytes
        if not image.isNull():
            window.set_image(image)

    def _on_error(self, message: str) -> None:
        # The session is over: the popup stayed open on its last frame and
        # the badge kept saying connected.
        self._disconnect()
        QMessageBox.warning(self, _t("rd_quick_connect_btn"), message)

    def _open_screen_window(self, title: str) -> None:
        if self._screen_window is None:
            window = RemoteScreenWindow(title, parent=self)
            window.closed.connect(self._on_window_closed)
            wire_remote_input(window, self._send_input)
            # Phase 1.4: drop a local file onto the remote screen window
            # and the viewer uploads it straight to the host.
            window.files_dropped.connect(self._on_files_dropped)
            self._screen_window = window
        # If frames arrived before this window existed (race with the
        # motion-dedup capture path), apply the most recent now.
        if self._pending_frame is not None:
            image = QImage.fromData(self._pending_frame, "JPEG")  # type: ignore[arg-type]  # reason: the stub says bytes; PySide6 raises ValueError for bytes
            if not image.isNull():
                self._screen_window.set_image(image)
        self._screen_window.show()
        self._screen_window.raise_()
        self._screen_window.activateWindow()

    def _send_input(self, action: dict) -> None:
        """Forward one input action from the popup to the live viewer."""
        viewer = self._own_viewer()
        if viewer is None or not viewer.connected:
            return
        try:
            viewer.send_input(action)
        except OSError as error:
            self._error_arrived.emit(str(error))

    def _on_files_dropped(self, paths) -> None:
        """Upload each dropped file to the host's home directory."""
        viewer = self._own_viewer()
        if viewer is None or not viewer.connected:
            return
        # send_file streams the whole file over the session's socket: off the
        # GUI thread, one batch at a time, so the popup keeps painting frames.
        if not self._uploads.start(
                functools.partial(_upload_to_home, viewer, [str(path) for path in paths])):
            QMessageBox.information(self, _t("rd_quick_connect_btn"), _t("rd_file_busy"))
            return
        self._refresh_status()

    def _on_upload_failed(self, error: object) -> None:
        QMessageBox.warning(self, _t("rd_quick_connect_btn"), str(error))

    def _close_screen_window(self) -> None:
        window = self._screen_window
        self._screen_window = None
        if window is None:
            return
        try:
            window.closed.disconnect(self._on_window_closed)
        except (RuntimeError, TypeError):
            pass
        window.hide()
        window.deleteLater()

    def _on_window_closed(self) -> None:
        # Either transport: closing a ws:// popup left its session running.
        if self._own_viewer() is not None:
            self._disconnect()

    # --- status -------------------------------------------------------

    def _refresh_status(self) -> None:
        self._refresh_host_status()
        self._refresh_viewer_status()

    def _refresh_host_status(self) -> None:
        status = registry.host_status()
        if status["running"]:
            host_id = status.get("host_id") or ""
            self._host_id_label.setText(
                format_host_id(host_id) if host_id else "---"
            )
            self._host_badge.set_state(
                "running",
                _t("rd_quick_hosting")
                .replace("{port}", str(status["port"]))
                .replace("{n}", str(status["connected_clients"])),
            )
        else:
            self._host_id_label.setText("---")
            self._host_badge.set_state(
                "stopped", _t("rd_quick_not_hosting"),
            )

    def _refresh_viewer_status(self) -> None:
        # Only this screen's own session, on either transport.
        viewer = self._own_viewer()
        if viewer is not None and viewer.connected:
            sending = self._uploads.running
            self._viewer_badge.set_state("live", _t(
                "rd_file_sending").replace("{name}", "") if sending else _t("rd_quick_connected"))
        elif self._connect_task is not None:
            self._viewer_badge.set_state("idle", _t("rd_viewer_connecting"))
        else:
            self._viewer_badge.set_state(
                "idle", _t("rd_quick_disconnected"),
            )


def _upload_to_home(viewer: Any, paths: List[str]) -> int:
    """Worker thread: send each file to the host's home directory; stops at the first failure."""
    for path in paths:
        viewer.send_file(path, "~/" + Path(path).name)
    return len(paths)


__all__ = ["QuickConnectScreen"]
