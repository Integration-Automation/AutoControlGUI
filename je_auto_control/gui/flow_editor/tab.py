"""Flow Editor tab: visual node-based view of a script.

Round-trips to the same JSON action format the list-based Script
Builder uses, so the two views stay compatible. The list editor is
still the place to edit complex nested branches; this tab is a clear
visual map of what the script will do.
"""
import json
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QGraphicsView, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.flow_editor.scene import FlowGraphScene
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.gui.script_builder.step_model import (
    Step, actions_to_steps, steps_to_actions,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class FlowEditorTab(TranslatableMixin, QWidget):
    """Visual node view of the current script (read + export)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._scene = FlowGraphScene(self)
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHints(self._view.renderHints())
        self._view.setDragMode(QGraphicsView.RubberBandDrag)
        self._steps: List[Step] = []
        self._inspector = QTextEdit()
        self._inspector.setReadOnly(True)
        self._status = QLabel()
        self._scene.node_selected.connect(self._on_node_selected)
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_translations()

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        for key, slot in (
                ("flow_open_btn", self._on_open),
                ("flow_save_btn", self._on_save),
                ("flow_zoom_in_btn", self._on_zoom_in),
                ("flow_zoom_out_btn", self._on_zoom_out),
                ("flow_fit_btn", self._on_fit),
        ):
            btn = QPushButton()
            btn.setObjectName(key)
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)
        toolbar.addStretch()
        root.addLayout(toolbar)
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._view)
        splitter.addWidget(self._inspector)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)
        root.addWidget(self._status)
        self._apply_translations()

    def _apply_translations(self) -> None:
        for key in ("flow_open_btn", "flow_save_btn",
                     "flow_zoom_in_btn", "flow_zoom_out_btn",
                     "flow_fit_btn"):
            widget = self.findChild(QPushButton, key)
            if widget is not None:
                widget.setText(_t(key))
        self._inspector.setPlaceholderText(_t("flow_inspector_placeholder"))

    # --- public ----------------------------------------------------

    def load_steps(self, steps: List[Step]) -> None:
        """Replace the visible graph from a pre-parsed step list."""
        self._steps = list(steps)
        layout = self._scene.load(self._steps)
        self._status.setText(
            _t("flow_loaded").replace("{count}", str(len(layout.nodes))),
        )

    def steps(self) -> List[Step]:
        return list(self._steps)

    # --- toolbar actions -------------------------------------------

    def _on_open(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self, _t("flow_open_btn"), "", "JSON (*.json);;All (*)",
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fp:
                actions = json.load(fp)
            steps = actions_to_steps(actions)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, _t("flow_open_btn"), str(error))
            return
        self.load_steps(steps)

    def _on_save(self) -> None:
        if not self._steps:
            self._status.setText(_t("flow_empty"))
            return
        path, _selected = QFileDialog.getSaveFileName(
            self, _t("flow_save_btn"), "", "JSON (*.json)",
        )
        if not path:
            return
        try:
            actions = steps_to_actions(self._steps)
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(actions, fp, indent=2, ensure_ascii=False)
        except (OSError, ValueError, TypeError) as error:
            QMessageBox.warning(self, _t("flow_save_btn"), str(error))
            return
        self._status.setText(
            _t("flow_saved").replace("{path}", str(path)),
        )

    def _on_zoom_in(self) -> None:
        self._view.scale(1.2, 1.2)

    def _on_zoom_out(self) -> None:
        self._view.scale(1 / 1.2, 1 / 1.2)

    def _on_fit(self) -> None:
        rect = self._scene.itemsBoundingRect()
        if rect.isEmpty():
            return
        self._view.fitInView(rect, Qt.KeepAspectRatio)

    def _on_node_selected(self, path: Tuple) -> None:
        step = _resolve_step(self._steps, path)
        if step is None:
            return
        body_keys = list(step.bodies.keys())
        self._inspector.setPlainText(
            f"command: {step.command}\n"
            f"params: {json.dumps(step.params, indent=2, ensure_ascii=False)}\n"
            f"bodies: {body_keys}",
        )


def _resolve_step(roots: List[Step], path: Tuple) -> Optional[Step]:
    if not path:
        return None
    head, *tail = path
    if not isinstance(head, int) or head >= len(roots):
        return None
    step = roots[head]
    for segment in tail:
        if not (isinstance(segment, tuple) and len(segment) == 2):
            return None
        body_key, child_index = segment
        children = step.bodies.get(body_key, [])
        if not isinstance(child_index, int) or child_index >= len(children):
            return None
        step = children[child_index]
    return step


__all__ = ["FlowEditorTab"]
