"""Triggers tab: image / window / pixel / file event watchers."""
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.triggers.trigger_engine import (
    FilePathTrigger, ImageAppearsTrigger, PixelColorTrigger,
    WindowAppearsTrigger, default_trigger_engine,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


_TYPE_KEYS = (
    "tr_type_image", "tr_type_window", "tr_type_pixel", "tr_type_file",
)


class TriggersTab(TranslatableMixin, QWidget):
    """Build triggers, run the engine, inspect the table."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._script_input = QLineEdit()
        self._repeat_check = self._tr(QCheckBox(), "tr_repeat")
        self._repeat_check.setChecked(True)
        self._type_combo = QComboBox()
        self._apply_type_combo()
        self._stack = QStackedWidget()
        self._image_widgets = self._build_image_form()
        self._window_widgets = self._build_window_form()
        self._pixel_widgets = self._build_pixel_form()
        self._file_widgets = self._build_file_form()
        self._running = False
        self._status = QLabel()
        self._apply_status()
        self._table = QTableWidget(0, 5)
        self._apply_table_headers()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self._build_layout()
        self._type_combo.currentIndexChanged.connect(self._stack.setCurrentIndex)

    def _apply_type_combo(self) -> None:
        current = self._type_combo.currentIndex()
        self._type_combo.blockSignals(True)
        self._type_combo.clear()
        self._type_combo.addItems([_t(k) for k in _TYPE_KEYS])
        if 0 <= current < self._type_combo.count():
            self._type_combo.setCurrentIndex(current)
        self._type_combo.blockSignals(False)

    def _apply_table_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([
            _t("tr_col_id"), _t("tr_col_type"),
            _t("tr_col_detail"), _t("tr_col_fired"), _t("tr_col_enabled"),
        ])

    def _apply_status(self) -> None:
        key = "tr_engine_running" if self._running else "tr_engine_stopped"
        self._status.setText(_t(key))

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_type_combo()
        self._apply_table_headers()
        self._apply_status()
        self._refresh()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        form_top = QHBoxLayout()
        form_top.addWidget(self._tr(QLabel(), "tr_script_label"))
        form_top.addWidget(self._script_input, stretch=1)
        browse = self._tr(QPushButton(), "browse")
        browse.clicked.connect(self._browse_script)
        form_top.addWidget(browse)
        form_top.addWidget(self._repeat_check)
        form_top.addWidget(self._tr(QLabel(), "tr_type_label"))
        form_top.addWidget(self._type_combo)
        add_btn = self._tr(QPushButton(), "tr_add")
        add_btn.clicked.connect(self._on_add)
        form_top.addWidget(add_btn)
        root.addLayout(form_top)
        root.addWidget(self._stack)
        root.addWidget(self._table, stretch=1)

        ctl = QHBoxLayout()
        for key, handler in (
            ("tr_remove_selected", self._on_remove),
            ("tr_start_engine", self._on_start),
            ("tr_stop_engine", self._on_stop),
        ):
            btn = self._tr(QPushButton(), key)
            btn.clicked.connect(handler)
            ctl.addWidget(btn)
        ctl.addStretch()
        root.addLayout(ctl)
        root.addWidget(self._status)

    def _build_image_form(self) -> dict:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        path_input = QLineEdit()
        threshold_input = QLineEdit("0.8")
        browse = self._tr(QPushButton(), "browse")
        browse.clicked.connect(lambda: self._browse_image(path_input))
        layout.addWidget(self._tr(QLabel(), "tr_image_label"))
        layout.addWidget(path_input, stretch=1)
        layout.addWidget(browse)
        layout.addWidget(self._tr(QLabel(), "tr_threshold_label"))
        layout.addWidget(threshold_input)
        self._stack.addWidget(widget)
        return {"path": path_input, "threshold": threshold_input}

    def _build_window_form(self) -> dict:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        title_input = QLineEdit()
        layout.addWidget(self._tr(QLabel(), "tr_title_contains_label"))
        layout.addWidget(title_input, stretch=1)
        self._stack.addWidget(widget)
        return {"title": title_input}

    def _build_pixel_form(self) -> dict:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        x_input = QLineEdit("0")
        y_input = QLineEdit("0")
        r_input = QLineEdit("0")
        g_input = QLineEdit("0")
        b_input = QLineEdit("0")
        tol_input = QLineEdit("8")
        for label, field in (("X:", x_input), ("Y:", y_input),
                             ("R:", r_input), ("G:", g_input), ("B:", b_input),
                             ("\u00b1:", tol_input)):
            layout.addWidget(QLabel(label))
            layout.addWidget(field)
        self._stack.addWidget(widget)
        return {"x": x_input, "y": y_input, "r": r_input,
                "g": g_input, "b": b_input, "tol": tol_input}

    def _build_file_form(self) -> dict:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        path_input = QLineEdit()
        browse = self._tr(QPushButton(), "browse")
        browse.clicked.connect(lambda: self._browse_watch(path_input))
        layout.addWidget(self._tr(QLabel(), "tr_watch_label"))
        layout.addWidget(path_input, stretch=1)
        layout.addWidget(browse)
        self._stack.addWidget(widget)
        return {"path": path_input}

    def _browse_script(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("tr_dialog_select_script"), "", "JSON (*.json)",
        )
        if path:
            self._script_input.setText(path)

    def _browse_image(self, target: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, _t("tr_dialog_select_image"), "", "Images (*.png *.jpg *.bmp)",
        )
        if path:
            target.setText(path)

    def _browse_watch(self, target: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, _t("tr_dialog_select_file"), "")
        if path:
            target.setText(path)

    def _on_add(self) -> None:
        script = self._script_input.text().strip()
        if not script:
            QMessageBox.warning(self, "Error", "Script path is required")
            return
        try:
            trigger = self._build_trigger(script)
        except ValueError as error:
            QMessageBox.warning(self, "Error", str(error))
            return
        default_trigger_engine.add(trigger)
        self._refresh()

    def _build_trigger(self, script: str):
        idx = self._type_combo.currentIndex()
        common = {"trigger_id": "", "script_path": script,
                  "repeat": self._repeat_check.isChecked()}
        if idx == 0:
            return ImageAppearsTrigger(
                image_path=self._image_widgets["path"].text().strip(),
                threshold=float(self._image_widgets["threshold"].text() or "0.8"),
                **common,
            )
        if idx == 1:
            return WindowAppearsTrigger(
                title_substring=self._window_widgets["title"].text().strip(),
                **common,
            )
        if idx == 2:
            w = self._pixel_widgets
            return PixelColorTrigger(
                x=int(w["x"].text() or "0"), y=int(w["y"].text() or "0"),
                target_rgb=(int(w["r"].text() or "0"),
                            int(w["g"].text() or "0"),
                            int(w["b"].text() or "0")),
                tolerance=int(w["tol"].text() or "8"),
                **common,
            )
        return FilePathTrigger(
            watch_path=self._file_widgets["path"].text().strip(),
            **common,
        )

    def _on_remove(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        tid = self._table.item(row, 0).text()
        default_trigger_engine.remove(tid)
        self._refresh()

    def _on_start(self) -> None:
        default_trigger_engine.start()
        self._timer.start()
        self._running = True
        self._apply_status()

    def _on_stop(self) -> None:
        default_trigger_engine.stop()
        self._timer.stop()
        self._running = False
        self._apply_status()

    def _refresh(self) -> None:
        triggers = default_trigger_engine.list_triggers()
        self._table.setRowCount(len(triggers))
        yes = _t("tr_yes")
        no = _t("tr_no")
        for row, trigger in enumerate(triggers):
            detail = _describe(trigger)
            for col, value in enumerate((
                trigger.trigger_id, type(trigger).__name__, detail,
                str(trigger.fired), yes if trigger.enabled else no,
            )):
                self._table.setItem(row, col, QTableWidgetItem(value))


def _describe(trigger) -> str:
    if isinstance(trigger, ImageAppearsTrigger):
        return f"img={trigger.image_path} th={trigger.threshold}"
    if isinstance(trigger, WindowAppearsTrigger):
        return f"title~{trigger.title_substring!r}"
    if isinstance(trigger, PixelColorTrigger):
        return f"({trigger.x},{trigger.y})={trigger.target_rgb} \u00b1{trigger.tolerance}"
    if isinstance(trigger, FilePathTrigger):
        return f"watch={trigger.watch_path}"
    return "?"
