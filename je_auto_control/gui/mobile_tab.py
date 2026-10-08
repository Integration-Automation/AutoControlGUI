"""Mobile tab: probe an Android / iOS device and run one mobile command on it.

A thin wrapper over the headless API: the command list is
``je_auto_control.MOBILE_COMMANDS``, running one is
``je_auto_control.run_mobile_command`` and probing is
``je_auto_control.device_setup_report``. Nothing here is unreachable from an
action file. Probe and run talk to a device (adb, WebDriverAgent), so they run
off the GUI thread, one at a time.
"""
import functools
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFormLayout, QLabel, QLineEdit, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import je_auto_control as ac
from je_auto_control.gui._dispose import release_resources
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._tab_task import TabTask
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)

_COLS = ("mob_col_capability", "mob_col_state", "mob_col_reason")
_PLATFORMS = (("android", "Android"), ("ios", "iOS"))
#: Parameters the tab fills from its own fields.
_ADDRESS = ("serial", "url", "adb_path")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _run_command(name: str, params: Dict[str, Any]) -> Any:
    """Worker thread: one mobile command."""
    return ac.run_mobile_command(name, params)


def _probe(platform: str, device_id: str, adb_path: Optional[str]) -> Dict[str, Any]:
    """Worker thread: open the device and report what it can do."""
    context = ac.DeviceContext(platform, device_id, adb_path=adb_path)
    with ac.open_device(context) as session:
        return ac.device_setup_report(session).to_dict()


class MobileTab(TranslatableMixin, QWidget):
    """Pick a device and a command, edit its parameters, see the result."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._platform = QComboBox()
        for key, label in _PLATFORMS:
            self._platform.addItem(label, key)
        self._device = QLineEdit()
        self._device.setPlaceholderText("emulator-5554  /  http://192.168.1.20:8100")
        self._adb_path = QLineEdit()
        self._command = QComboBox()
        self._params = QPlainTextEdit()
        self._params.setPlaceholderText('{"x": 100, "y": 200}')
        self._result = QPlainTextEdit()
        self._result.setReadOnly(True)
        self._table = QTableWidget(0, len(_COLS))
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._note = QLabel()
        self._note.setWordWrap(True)
        self._runs = TabTask(self)   # tag: "probe" or "run"
        self._runs.result.connect(self._show_outcome)
        self._runs.error.connect(self._show_error)
        self._apply_headers()
        self._build_layout()
        self._platform.currentIndexChanged.connect(self._reload_commands)
        self._reload_commands()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_headers()

    def _apply_headers(self) -> None:
        self._table.setHorizontalHeaderLabels([_t(key) for key in _COLS])

    def _build_layout(self) -> None:
        # Probe / run / fill live in the Actions menu; the tab keeps only the
        # inputs, the capability table and the result view.
        root = QVBoxLayout(self)
        root.addWidget(self._tr(self._note, "mob_untested"))
        form = QFormLayout()
        for key, widget in (("mob_platform", self._platform), ("mob_device", self._device),
                            ("mob_adb_path", self._adb_path), ("mob_command", self._command)):
            form.addRow(self._tr(QLabel(), key), widget)
        root.addLayout(form)
        root.addWidget(self._tr(QLabel(), "mob_params"))
        root.addWidget(self._params)
        root.addWidget(self._table, stretch=1)
        root.addWidget(self._tr(QLabel(), "mob_result"))
        root.addWidget(self._result, stretch=1)

    def dispose(self) -> None:
        """Release what the tab holds beyond its widgets: the command still running in the background.

        A script run is stopped; other work cannot be interrupted, so it runs to its end and its
        result is dropped. Called by ``close_tab(key, release=True)``; safe to call twice.
        """
        release_resources(self)

    def menu_actions(self) -> List[Tuple[str, Callable[[], None]]]:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("mob_probe", self._on_probe),
            ("mob_run", self._on_run),
            ("mob_fill_params", self._on_fill_params),
        ]

    # --- state the menu handlers and tests read or set ---------------------

    def command_names(self) -> List[str]:
        """Every command the tab offers, across both platforms."""
        return [command.name for command in ac.MOBILE_COMMANDS]

    def set_target(self, platform: str, device_id: str = "", adb_path: str = "") -> None:
        """Select the platform and fill the device fields."""
        self._platform.setCurrentIndex(max(0, self._platform.findData(platform)))
        self._device.setText(device_id)
        self._adb_path.setText(adb_path)

    def set_command(self, name: str, params: Optional[Dict[str, Any]] = None) -> None:
        """Select a command and fill its parameters."""
        self._command.setCurrentIndex(max(0, self._command.findData(name)))
        self._params.setPlainText(json.dumps(params or {}))

    def result_text(self) -> str:
        """What the result view shows."""
        return self._result.toPlainText()

    def capability_rows(self) -> Dict[str, str]:
        """Capability name to state, as the table shows it."""
        return {self._table.item(row, 0).text(): self._table.item(row, 1).text()
                for row in range(self._table.rowCount())}

    def _current_platform(self) -> str:
        return str(self._platform.currentData())

    def _reload_commands(self) -> None:
        platform = self._current_platform()
        self._command.clear()
        for command in ac.MOBILE_COMMANDS:
            if command.platform == platform:
                self._command.addItem(f"{command.label}  ({command.name})", command.name)

    def _address(self, command: Any) -> Dict[str, Any]:
        """The address parameters this command takes, from the tab's fields."""
        names = {param.name for param in command.params}
        key = "serial" if command.platform == "android" else "url"
        values = {key: self._device.text().strip(), "adb_path": self._adb_path.text().strip()}
        return {name: value for name, value in values.items() if value and name in names}

    def _show_error(self, error: object) -> None:
        self._result.setPlainText(_t("mob_error").replace("{error}", str(error)))

    def _show_outcome(self, value: Any) -> None:
        if self._runs.tag == "probe":
            self._render(value)
            return
        self._result.setPlainText(json.dumps(value, indent=2, ensure_ascii=False, default=str))

    def _start(self, work: Callable[[], Any], tag: str) -> None:
        if self._runs.start(work, tag=tag):
            self._result.setPlainText(_t("task_running"))

    # --- Actions menu handlers ---------------------------------------------

    def _on_fill_params(self) -> None:
        command = self._selected()
        if command is None:
            return
        template = {param.name: param.default for param in command.params
                    if param.name not in _ADDRESS and (param.required or param.default is not None)}
        self._params.setPlainText(json.dumps(template, indent=2))

    def _selected(self) -> Any:
        name = self._command.currentData()
        return next((c for c in ac.MOBILE_COMMANDS if c.name == name), None)

    def _on_run(self) -> None:
        command = self._selected()
        if command is None:
            return
        try:
            params = json.loads(self._params.toPlainText() or "{}")
            if not isinstance(params, dict):
                raise ValueError("parameters must be a JSON object")
        except (ValueError, TypeError) as error:
            self._show_error(error)
            return
        self._start(functools.partial(_run_command, command.name, {**self._address(command), **params}),
                    "run")

    def _on_probe(self) -> None:
        self._start(functools.partial(_probe, self._current_platform(), self._device.text().strip(),
                                      self._adb_path.text().strip() or None), "probe")

    def _render(self, report: Dict[str, Any]) -> None:
        capabilities = report.pop("capabilities")
        self._table.setRowCount(len(capabilities))
        for row, (name, capability) in enumerate(capabilities.items()):
            for col, text in enumerate((name, capability["state"], capability["reason"])):
                item = QTableWidgetItem(str(text))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(row, col, item)
        self._result.setPlainText(json.dumps(report, indent=2, ensure_ascii=False))
