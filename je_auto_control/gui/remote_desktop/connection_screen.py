"""Quick Connect — single-screen AnyDesk-style entry for Remote Desktop.

The Quick Connect surface is what an operator sees first when they open
the Remote Desktop tab. It replaces the per-transport sub-tabs as the
default landing view; everything else (manual SDP, WSS, custom codecs,
TLS cert pinning) is one click away in the unchanged Advanced sub-tabs.

Design:
  * Left half — 'This machine': huge Host ID + token + Start/Stop.
  * Right half — 'Connect to': ``host:port`` input + Connect + Recent.
  * Status badges on both halves; popup viewer window on connect.

Transport for the viewer side defaults to direct TCP (no extras needed).
Operators who want WebRTC signaling, WSS, or manual SDP exchange go to
the Advanced sub-tabs.
"""
import secrets
import threading
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.remote_desktop._helpers import _StatusBadge, _t
from je_auto_control.gui.remote_desktop.remote_screen_window import (
    RemoteScreenWindow,
)
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
from je_auto_control.utils.remote_desktop.registry import registry
from je_auto_control.utils.remote_desktop.wake_on_lan import (
    send_magic_packet,
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
_TCP_RECENT_PREFIX = "tcp://"
_RECENT_MAX = 20
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


class QuickConnectScreen(TranslatableMixin, QWidget):
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

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
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
        self._book = default_address_book()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(self._STATUS_INTERVAL_MS)
        self._refresh_timer.timeout.connect(self._refresh_status)
        # ``Qt.QueuedConnection`` so the slot is invoked on the GUI thread
        # even though the signal is emitted from the host's accept thread.
        self._approval_requested.connect(
            self._show_approval_dialog, Qt.ConnectionType.QueuedConnection,
        )
        self._build_layout()
        self._apply_placeholders()
        self._refresh_recent()
        self._refresh_status()
        self._refresh_timer.start()

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
        registry.disconnect_viewer()
        registry.stop_host()
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
        registry._host = host  # noqa: SLF001  centralised lifecycle ownership
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
        try:
            registry.stop_host()
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

    def _do_tcp_connect(self, host: str, port: int, token: str) -> None:
        registry.disconnect_viewer()
        try:
            viewer = RemoteDesktopViewer(
                host=host, port=port, token=token,
                on_frame=self._on_frame,
                on_error=lambda exc: self._on_error(str(exc)),
                on_cursor=self._on_remote_cursor,
            )
            viewer.connect(timeout=5.0)
        except (OSError, RuntimeError) as error:
            # AuthenticationError is a subclass of RuntimeError; the
            # tuple above already catches it.
            QMessageBox.warning(self, _t("rd_quick_connect_btn"), str(error))
            return
        registry._viewer = viewer  # noqa: SLF001  centralised lifecycle ownership
        self._remember_tcp(host, port)
        self._open_screen_window(f"{host}:{port}")
        self._refresh_status()

    def _do_ws_connect(self, target: ConnectTarget, token: str) -> None:
        host = target.host or ""
        port = target.port or 0
        path = target.path or "/"
        registry.disconnect_ws_viewer()
        try:
            viewer = WebSocketDesktopViewer(
                host=host, port=port, token=token, path=path,
                on_frame=self._on_frame,
                on_error=lambda exc: self._on_error(str(exc)),
                on_cursor=self._on_remote_cursor,
            )
            viewer.connect(timeout=5.0)
        except (OSError, RuntimeError) as error:
            # AuthenticationError is a subclass of RuntimeError; the
            # tuple above already catches it.
            QMessageBox.warning(self, _t("rd_quick_connect_btn"), str(error))
            return
        registry._ws_viewer = viewer  # noqa: SLF001  centralised lifecycle ownership
        scheme = "wss" if target.kind == "wss" else "ws"
        self._remember_url(f"{scheme}://{host}:{port}{path}")
        self._open_screen_window(f"{scheme}://{host}:{port}")
        self._refresh_status()

    def _on_remote_cursor(self, x: int, y: int) -> None:
        """Network-thread cursor update; forward to the popup display."""
        window = self._screen_window
        if window is None:
            return
        # ``set_remote_cursor`` calls ``update()`` which is thread-safe
        # on the QWidget API surface — internally Qt marshals the paint
        # request to the GUI thread for us.
        try:
            window.display.set_remote_cursor(x, y)
        except RuntimeError:
            # Window was destroyed between the null check and the call.
            pass

    def _handoff_to_webrtc(self, host_id: str, token: str) -> None:
        """Emit the signal so the parent tab can switch + prefill."""
        self.webrtc_handoff_requested.emit(host_id, token)

    def _disconnect(self) -> None:
        # Both transports may be live; clear whichever slot was filled
        # so the operator does not need to remember which they used.
        registry.disconnect_viewer()
        registry.disconnect_ws_viewer()
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
        image = QImage.fromData(payload, "JPEG")
        if not image.isNull():
            window.set_image(image)

    def _on_error(self, message: str) -> None:
        QMessageBox.warning(self, _t("rd_quick_connect_btn"), message)

    def _open_screen_window(self, title: str) -> None:
        if self._screen_window is None:
            window = RemoteScreenWindow(title, parent=self)
            window.closed.connect(self._on_window_closed)
            # Phase 1.4: drop a local file onto the remote screen window
            # and the viewer uploads it straight to the host.
            window.files_dropped.connect(self._on_files_dropped)
            self._screen_window = window
        # If frames arrived before this window existed (race with the
        # motion-dedup capture path), apply the most recent now.
        if self._pending_frame is not None:
            image = QImage.fromData(self._pending_frame, "JPEG")
            if not image.isNull():
                self._screen_window.set_image(image)
        self._screen_window.show()
        self._screen_window.raise_()
        self._screen_window.activateWindow()

    def _on_files_dropped(self, paths) -> None:
        """Upload each dropped file to the host's home directory."""
        viewer = registry.viewer or registry._ws_viewer  # noqa: SLF001
        if viewer is None or not viewer.connected:
            return
        for path in paths:
            from pathlib import Path
            try:
                dest = "~/" + Path(path).name
                viewer.send_file(path, dest)
            except (OSError, RuntimeError) as error:
                QMessageBox.warning(
                    self, _t("rd_quick_connect_btn"), str(error),
                )
                return

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
        if registry.viewer is not None:
            self._disconnect()

    # --- recent connections ------------------------------------------

    def _remember_tcp(self, host: str, port: int) -> None:
        self._remember_url(f"{_TCP_RECENT_PREFIX}{host}:{port}")

    def _remember_url(self, url: str) -> None:
        """Record ``url`` in the address book so it shows up in Recent."""
        try:
            self._book.upsert(host_id=url, server_url=url, label="")
        except (ValueError, OSError):
            return
        self._refresh_recent()

    def _refresh_recent(self) -> None:
        self._recent.clear()
        entries = self._book.list_entries()
        entries.sort(key=lambda e: e.get("last_used", ""), reverse=True)
        for entry in entries[:_RECENT_MAX]:
            host_id = str(entry.get("host_id", ""))
            label = str(entry.get("label") or host_id)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, host_id)
            self._recent.addItem(item)

    def _on_recent_activated(self, item: QListWidgetItem) -> None:
        target = item.data(Qt.ItemDataRole.UserRole) or item.text()
        self._connect_target.setText(str(target))

    def _on_recent_menu(self, pos) -> None:
        """Right-click menu on the Recent list: edit MAC, send WoL."""
        item = self._recent.itemAt(pos)
        if item is None:
            return
        host_id = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
        entry = self._find_address_book_entry(host_id)
        menu = QMenu(self._recent)
        wake = menu.addAction(_t("rd_quick_wake_host"))
        edit = menu.addAction(_t("rd_quick_edit_mac"))
        chosen = menu.exec(self._recent.mapToGlobal(pos))
        if chosen is wake:
            self._send_wake_on_lan(entry, host_id)
        elif chosen is edit:
            self._edit_recent_mac(entry, host_id)

    def _find_address_book_entry(self, host_id: str):
        for entry in self._book.list_entries():
            if entry.get("host_id") == host_id:
                return entry
        return None

    def _send_wake_on_lan(self, entry, host_id: str) -> None:
        mac = (entry or {}).get("mac_address") if entry else None
        if not mac:
            mac, ok = QInputDialog.getText(
                self, _t("rd_quick_wake_host"),
                _t("rd_quick_wol_mac_prompt"),
            )
            if not ok or not mac:
                return
            self._save_mac_to_book(host_id, mac)
        broadcast = (entry or {}).get("broadcast_address") if entry else None
        try:
            send_magic_packet(
                mac, broadcast=broadcast or "255.255.255.255",
            )
        except (OSError, ValueError) as error:
            QMessageBox.warning(
                self, _t("rd_quick_wake_host"), str(error),
            )
            return
        QMessageBox.information(
            self, _t("rd_quick_wake_host"),
            _t("rd_quick_wol_sent").replace("{mac}", mac),
        )

    def _edit_recent_mac(self, entry, host_id: str) -> None:
        current = (entry or {}).get("mac_address") if entry else ""
        mac, ok = QInputDialog.getText(
            self, _t("rd_quick_edit_mac"),
            _t("rd_quick_wol_mac_prompt"),
            text=str(current or ""),
        )
        if not ok or not mac:
            return
        self._save_mac_to_book(host_id, mac)

    def _save_mac_to_book(self, host_id: str, mac: str) -> None:
        """Persist the MAC against the matching AddressBook entry."""
        for entry in self._book.list_entries():
            if entry.get("host_id") == host_id:
                try:
                    self._book.upsert(
                        host_id=host_id,
                        server_url=entry.get("server_url", host_id),
                        label=entry.get("label", ""),
                        mac_address=mac,
                    )
                except (ValueError, OSError):
                    return
                self._refresh_recent()
                return

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
        status = registry.viewer_status()
        if status["connected"]:
            self._viewer_badge.set_state("live", _t("rd_quick_connected"))
        else:
            self._viewer_badge.set_state(
                "idle", _t("rd_quick_disconnected"),
            )


__all__ = ["QuickConnectScreen"]
