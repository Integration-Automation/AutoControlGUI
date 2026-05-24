"""Trace Replay tab — scrub through a time-travel recording.

Loads a directory containing ``manifest.json`` + ``actions.jsonl``
written by :class:`JpegSequenceRecorder` and shows the screenshot at
the selected step plus the actions that ran in its window. Pure
display + navigation; the real timeline logic lives in
:class:`TraceReplayController` so it can be unit-tested without Qt.
"""
import json
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton, QSlider,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.time_travel import (
    ReplayState, TimelinePlayer, TraceReplayController,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


_ACTION_COLUMNS = ("timestamp", "action_name", "args", "error")


class TraceReplayTab(TranslatableMixin, QWidget):
    """Open a recording, scrub the timeline, inspect per-step actions."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._controller: Optional[TraceReplayController] = None
        self._frame_label = QLabel()
        self._frame_label.setAlignment(Qt.AlignCenter)
        self._frame_label.setMinimumSize(320, 240)
        self._frame_label.setStyleSheet("background-color: #1e1e1e;")
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.valueChanged.connect(self._on_slider_changed)
        self._status = QLabel()
        self._actions_table = QTableWidget(0, len(_ACTION_COLUMNS))
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_translations()

    # --- layout ---------------------------------------------------

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        controls = QHBoxLayout()
        for key, slot in (
                ("trace_open_btn", self._on_open),
                ("trace_first_btn", self._on_first),
                ("trace_prev_btn", self._on_prev),
                ("trace_next_btn", self._on_next),
                ("trace_last_btn", self._on_last),
        ):
            btn = QPushButton()
            btn.setObjectName(key)
            btn.clicked.connect(slot)
            controls.addWidget(btn)
        controls.addStretch()
        root.addLayout(controls)
        root.addWidget(self._slider)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._frame_label)
        splitter.addWidget(self._actions_table)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)
        root.addWidget(self._status)
        self._apply_translations()

    def _apply_translations(self) -> None:
        for key in ("trace_open_btn", "trace_first_btn",
                     "trace_prev_btn", "trace_next_btn", "trace_last_btn"):
            widget = self.findChild(QPushButton, key)
            if widget is not None:
                widget.setText(_t(key))
        headers = [_t(f"trace_col_{col}") for col in _ACTION_COLUMNS]
        self._actions_table.setHorizontalHeaderLabels(headers)

    # --- public ---------------------------------------------------

    def load_recording(self, directory: str) -> None:
        """Wire a freshly-opened recording into the slider + table."""
        player = TimelinePlayer(directory)
        self._controller = TraceReplayController(player)
        total = max(0, self._controller.total_steps - 1)
        self._slider.blockSignals(True)
        self._slider.setMaximum(total)
        self._slider.setValue(0)
        self._slider.blockSignals(False)
        self._render(self._controller.state())

    # --- handlers -------------------------------------------------

    def _on_open(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, _t("trace_open_btn"),
        )
        if directory:
            self.load_recording(directory)

    def _on_first(self) -> None:
        if self._controller is None:
            return
        self._render(self._controller.jump_to_start())

    def _on_last(self) -> None:
        if self._controller is None:
            return
        self._render(self._controller.jump_to_end())

    def _on_prev(self) -> None:
        if self._controller is None:
            return
        self._render(self._controller.step_backward())

    def _on_next(self) -> None:
        if self._controller is None:
            return
        self._render(self._controller.step_forward())

    def _on_slider_changed(self, value: int) -> None:
        if self._controller is None:
            return
        self._render(self._controller.seek(int(value)))

    # --- rendering ------------------------------------------------

    def _render(self, state: ReplayState) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(state.step)
        self._slider.blockSignals(False)
        self._status.setText(
            _t("trace_status")
            .replace("{step}", str(state.step + 1))
            .replace("{total}", str(max(state.total_steps, 1)))
            .replace("{seconds}", f"{state.relative_time_s:.2f}"),
        )
        self._render_frame(state)
        self._render_actions(state)

    def _render_frame(self, state: ReplayState) -> None:
        if (state.frame_filename is None or self._controller is None
                or self._controller.player.directory is None):
            self._frame_label.clear()
            return
        path = self._controller.player.directory / state.frame_filename
        try:
            pixmap = QPixmap(str(path))
        except (OSError, RuntimeError):
            self._frame_label.clear()
            return
        if pixmap.isNull():
            self._frame_label.clear()
            return
        scaled = pixmap.scaled(
            self._frame_label.size(), Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._frame_label.setPixmap(scaled)

    def _render_actions(self, state: ReplayState) -> None:
        self._actions_table.setRowCount(len(state.actions))
        for row, action in enumerate(state.actions):
            values = (
                f"{float(action.get('timestamp', 0.0)):.3f}",
                str(action.get("action_name", "")),
                json.dumps(action.get("args") or {}, ensure_ascii=False),
                str(action.get("error") or ""),
            )
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._actions_table.setItem(row, col, item)
        self._actions_table.resizeColumnsToContents()


__all__ = ["TraceReplayTab"]
