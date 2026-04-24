"""Schema-driven form for editing a Step's parameters."""
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.script_builder.command_schema import (
    COMMAND_SPECS, CommandSpec, FieldSpec, FieldType,
)
from je_auto_control.gui.script_builder.step_model import Step


_EDITOR_BUILDERS: Dict[FieldType, Callable[["StepFormView", FieldSpec], QWidget]]


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class StepFormView(QWidget):
    """Right-pane editor for a single Step."""

    step_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._step: Optional[Step] = None
        self._editors: Dict[str, QWidget] = {}
        self._layout = QFormLayout(self)
        self._title = QLabel(_t("sb_no_step_selected"))
        self._layout.addRow(self._title)

    def retranslate(self) -> None:
        """Re-apply translated title and reload current step for label refresh."""
        if self._step is None:
            self._title.setText(_t("sb_no_step_selected"))
        else:
            self.load_step(self._step)

    def load_step(self, step: Optional[Step]) -> None:
        """Populate the form with fields for ``step``."""
        self._clear()
        self._step = step
        if step is None:
            self._title.setText(_t("sb_no_step_selected"))
            return
        spec = COMMAND_SPECS.get(step.command)
        if spec is None:
            self._title.setText(f"Unknown command: {step.command}")
            return
        self._title.setText(f"{spec.label}  ({spec.command})")
        for field_spec in spec.fields:
            editor = self._build_editor(field_spec)
            self._editors[field_spec.name] = editor
            self._layout.addRow(self._field_label(field_spec), editor)
        self._populate_from_step(spec, step)

    def _clear(self) -> None:
        while self._layout.rowCount() > 1:
            self._layout.removeRow(1)
        self._editors.clear()

    @staticmethod
    def _field_label(field_spec: FieldSpec) -> str:
        suffix = "" if not field_spec.optional else "  (optional)"
        return f"{field_spec.name}{suffix}"

    def _build_editor(self, spec: FieldSpec) -> QWidget:
        builder = _EDITOR_BUILDERS.get(spec.field_type, StepFormView._build_string)
        return builder(self, spec)

    def _build_string(self, spec: FieldSpec) -> QWidget:
        editor = QLineEdit()
        editor.setPlaceholderText(spec.placeholder)
        editor.textChanged.connect(self._commit_field)
        return editor

    def _build_int(self, spec: FieldSpec) -> QWidget:
        editor = QLineEdit()
        validator = QIntValidator()
        if spec.min_value is not None:
            validator.setBottom(int(spec.min_value))
        if spec.max_value is not None:
            validator.setTop(int(spec.max_value))
        editor.setValidator(validator)
        editor.setPlaceholderText(spec.placeholder)
        editor.textChanged.connect(self._commit_field)
        return editor

    def _build_float(self, spec: FieldSpec) -> QWidget:
        editor = QLineEdit()
        low = -1e9 if spec.min_value is None else float(spec.min_value)
        high = 1e9 if spec.max_value is None else float(spec.max_value)
        editor.setValidator(QDoubleValidator(low, high, 4))
        editor.setPlaceholderText(spec.placeholder)
        editor.textChanged.connect(self._commit_field)
        return editor

    def _build_bool(self, spec: FieldSpec) -> QWidget:
        del spec
        editor = QCheckBox()
        editor.toggled.connect(self._commit_field)
        return editor

    def _build_enum(self, spec: FieldSpec) -> QWidget:
        editor = QComboBox()
        for choice in spec.choices:
            editor.addItem(choice)
        editor.currentTextChanged.connect(self._commit_field)
        return editor

    def _build_file(self, spec: FieldSpec) -> QWidget:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        line = QLineEdit()
        line.setPlaceholderText(spec.placeholder)
        browse = QPushButton("...")
        browse.setMaximumWidth(30)
        browse.clicked.connect(lambda: self._browse_file(line))
        line.textChanged.connect(self._commit_field)
        row.addWidget(line)
        row.addWidget(browse)
        container.setProperty("line_edit", line)
        return container

    def _build_rgb(self, spec: FieldSpec) -> QWidget:
        editor = QLineEdit()
        editor.setPlaceholderText(spec.placeholder or "R,G,B")
        editor.textChanged.connect(self._commit_field)
        return editor

    def _browse_file(self, target: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select file")
        if path:
            target.setText(path)

    def _populate_from_step(self, spec: CommandSpec, step: Step) -> None:
        for field_spec in spec.fields:
            editor = self._editors[field_spec.name]
            value = step.params.get(field_spec.name, field_spec.default)
            _set_editor_value(editor, field_spec, value)

    def _commit_field(self) -> None:
        if self._step is None:
            return
        spec = COMMAND_SPECS.get(self._step.command)
        if spec is None:
            return
        new_params: Dict[str, Any] = {}
        for field_spec in spec.fields:
            editor = self._editors.get(field_spec.name)
            if editor is None:
                continue
            value = _read_editor_value(editor, field_spec)
            if value is None and field_spec.optional:
                continue
            new_params[field_spec.name] = value
        self._step.params = new_params
        self.step_changed.emit()


def _file_edit(editor: QWidget) -> Optional[QLineEdit]:
    line = editor.property("line_edit")
    return line if isinstance(line, QLineEdit) else None


def _set_text_value(editor: QWidget, value: Any) -> None:
    editor.setText("" if value is None else str(value))


def _set_rgb_value(editor: QWidget, value: Any) -> None:
    if isinstance(value, (list, tuple)):
        editor.setText(",".join(str(int(v)) for v in value))
    else:
        _set_text_value(editor, value)


def _set_file_value(editor: QWidget, value: Any) -> None:
    line = _file_edit(editor)
    if line is not None:
        _set_text_value(line, value)


_SETTERS = {
    FieldType.STRING: _set_text_value,
    FieldType.INT: _set_text_value,
    FieldType.FLOAT: _set_text_value,
    FieldType.BOOL: lambda e, v: e.setChecked(bool(v)),
    FieldType.ENUM: lambda e, v: e.setCurrentText(str(v) if v is not None else ""),
    FieldType.FILE_PATH: _set_file_value,
    FieldType.RGB: _set_rgb_value,
}


def _set_editor_value(editor: QWidget, spec: FieldSpec, value: Any) -> None:
    setter = _SETTERS.get(spec.field_type)
    if setter is not None:
        setter(editor, value)


def _read_string(editor: QWidget) -> Any:
    return editor.text() or None


def _read_int(editor: QWidget) -> Any:
    text = editor.text().strip()
    return int(text) if text else None


def _read_float(editor: QWidget) -> Any:
    text = editor.text().strip()
    return float(text) if text else None


def _read_file(editor: QWidget) -> Any:
    line = _file_edit(editor)
    return (line.text() or None) if line is not None else None


def _read_rgb(editor: QWidget) -> Any:
    text = editor.text().strip()
    if not text:
        return None
    parts = [p.strip() for p in text.split(",") if p.strip()]
    return [int(p) for p in parts]


_READERS = {
    FieldType.STRING: _read_string,
    FieldType.INT: _read_int,
    FieldType.FLOAT: _read_float,
    FieldType.BOOL: lambda e: bool(e.isChecked()),
    FieldType.ENUM: lambda e: e.currentText() or None,
    FieldType.FILE_PATH: _read_file,
    FieldType.RGB: _read_rgb,
}


def _read_editor_value(editor: QWidget, spec: FieldSpec) -> Any:
    reader = _READERS.get(spec.field_type)
    return reader(editor) if reader is not None else None


_EDITOR_BUILDERS = {
    FieldType.STRING: StepFormView._build_string,
    FieldType.INT: StepFormView._build_int,
    FieldType.FLOAT: StepFormView._build_float,
    FieldType.BOOL: StepFormView._build_bool,
    FieldType.ENUM: StepFormView._build_enum,
    FieldType.FILE_PATH: StepFormView._build_file,
    FieldType.RGB: StepFormView._build_rgb,
}
