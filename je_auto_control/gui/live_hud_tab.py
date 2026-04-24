"""Live HUD: mouse position, pixel colour under cursor and log tail."""
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.watcher.watcher import LogTail, MouseWatcher, PixelWatcher


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class LiveHUDTab(TranslatableMixin, QWidget):
    """Poll watchers and render a readable HUD."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._mouse = MouseWatcher()
        self._pixel = PixelWatcher()
        self._log_tail = LogTail(capacity=400)
        self._pos_suffix = " --"
        self._color_suffix = " --"
        self._pos_label = QLabel()
        self._color_label = QLabel()
        self._apply_position_labels()
        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)
        self._build_layout()

    def _apply_position_labels(self) -> None:
        self._pos_label.setText(_t("hud_mouse_prefix") + self._pos_suffix)
        self._color_label.setText(_t("hud_pixel_prefix") + self._color_suffix)

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_position_labels()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        status_group = self._tr(QGroupBox(), "hud_watchers_group")
        status_layout = QVBoxLayout()
        status_layout.addWidget(self._pos_label)
        status_layout.addWidget(self._color_label)
        status_group.setLayout(status_layout)
        root.addWidget(status_group)

        ctl = QHBoxLayout()
        start_btn = self._tr(QPushButton(), "hud_start")
        start_btn.clicked.connect(self._start)
        stop_btn = self._tr(QPushButton(), "hud_stop")
        stop_btn.clicked.connect(self._stop)
        clear_btn = self._tr(QPushButton(), "hud_clear")
        clear_btn.clicked.connect(self._log_view.clear)
        for btn in (start_btn, stop_btn, clear_btn):
            ctl.addWidget(btn)
        ctl.addStretch()
        root.addLayout(ctl)

        root.addWidget(self._tr(QLabel(), "hud_recent_log"))
        root.addWidget(self._log_view, stretch=1)

    def _start(self) -> None:
        self._log_tail.attach(autocontrol_logger)
        self._timer.start()

    def _stop(self) -> None:
        self._timer.stop()
        self._log_tail.detach(autocontrol_logger)

    def _tick(self) -> None:
        try:
            x, y = self._mouse.sample()
        except RuntimeError as error:
            self._pos_suffix = f" {error}"
            self._apply_position_labels()
            return
        self._pos_suffix = f" ({x}, {y})"
        rgb = self._pixel.sample(x, y)
        self._color_suffix = f" {rgb}" if rgb is not None else " n/a"
        self._apply_position_labels()
        lines = self._log_tail.snapshot()
        self._log_view.setPlainText("\n".join(lines))
        scrollbar = self._log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event) -> None:  # noqa: N802  # reason: Qt override
        self._stop()
        super().closeEvent(event)
