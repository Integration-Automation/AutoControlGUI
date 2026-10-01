"""VLM tab: describe a UI element in words and have a model find it."""
from typing import Optional

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._worker_thread import CallWorker, WorkerHandle, start_worker
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.vision.vlm_api import (
    click_by_description, locate_by_description,
)


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


class VLMTab(TranslatableMixin, QWidget):
    """Drive a vision-language model to locate or click described elements."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._description = QLineEdit()
        self._model = QLineEdit()
        self._status = QLabel()
        self._last_result = QLabel()
        self._vlm_thread: Optional[WorkerHandle] = None
        self._apply_placeholders()
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_placeholders()

    def _apply_placeholders(self) -> None:
        self._description.setPlaceholderText(_t("vlm_desc_placeholder"))
        self._model.setPlaceholderText(_t("vlm_model_placeholder"))

    def _build_layout(self) -> None:
        # Locate/click commands run from the Actions menu; the tab keeps
        # only the description/model inputs and the result labels.
        root = QVBoxLayout(self)
        desc_row = QHBoxLayout()
        desc_row.addWidget(self._tr(QLabel(), "vlm_desc_label"))
        desc_row.addWidget(self._description, stretch=1)
        root.addLayout(desc_row)
        model_row = QHBoxLayout()
        model_row.addWidget(self._tr(QLabel(), "vlm_model_label"))
        model_row.addWidget(self._model, stretch=1)
        root.addLayout(model_row)
        root.addWidget(self._last_result)
        root.addWidget(self._status)
        root.addStretch()

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("vlm_locate", self._on_locate),
            ("vlm_click", self._on_click),
        ]

    def _collect_inputs(self):
        description = self._description.text().strip()
        if not description:
            self._status.setText(_t("vlm_desc_required"))
            return None
        model = self._model.text().strip() or None
        return description, model

    def _run_off_gui_thread(self, call, on_done) -> None:
        """The VLM round trip (network, seconds) froze the window on the GUI thread."""
        if self._vlm_thread is not None:
            return
        self._vlm_thread = start_worker(self, CallWorker(call), on_done=on_done,
                                        on_fail=self._show_error, on_thread_done=self._on_vlm_done)

    def _on_vlm_done(self) -> None:
        self._vlm_thread = None

    def _show_error(self, message: str) -> None:
        self._status.setText(f"{_t('vlm_error')}: {message}")

    def _on_locate(self) -> None:
        inputs = self._collect_inputs()
        if inputs is None:
            return
        description, model = inputs
        self._run_off_gui_thread(lambda: locate_by_description(description, model=model), self._show_located)

    def _show_located(self, coords) -> None:
        if coords is None:
            self._status.setText(_t("vlm_not_found"))
            self._last_result.setText("")
            return
        self._last_result.setText(
            _t("vlm_result").replace("{x}", str(coords[0]))
                             .replace("{y}", str(coords[1])),
        )
        self._status.setText(_t("vlm_ok"))

    def _on_click(self) -> None:
        inputs = self._collect_inputs()
        if inputs is None:
            return
        description, model = inputs
        self._run_off_gui_thread(
            lambda: click_by_description(description, model=model),
            lambda ok: self._status.setText(_t("vlm_ok") if ok else _t("vlm_not_found")))
