"""VLM tab: describe a UI element in words and have a model find it."""
from typing import Optional

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
from je_auto_control.utils.vision.backends.base import VLMNotAvailableError
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
        self._apply_placeholders()
        self._build_layout()

    def retranslate(self) -> None:
        TranslatableMixin.retranslate(self)
        self._apply_placeholders()

    def _apply_placeholders(self) -> None:
        self._description.setPlaceholderText(_t("vlm_desc_placeholder"))
        self._model.setPlaceholderText(_t("vlm_model_placeholder"))

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        desc_row = QHBoxLayout()
        desc_row.addWidget(self._tr(QLabel(), "vlm_desc_label"))
        desc_row.addWidget(self._description, stretch=1)
        root.addLayout(desc_row)
        model_row = QHBoxLayout()
        model_row.addWidget(self._tr(QLabel(), "vlm_model_label"))
        model_row.addWidget(self._model, stretch=1)
        root.addLayout(model_row)
        btn_row = QHBoxLayout()
        locate_btn = self._tr(QPushButton(), "vlm_locate")
        locate_btn.clicked.connect(self._on_locate)
        click_btn = self._tr(QPushButton(), "vlm_click")
        click_btn.clicked.connect(self._on_click)
        btn_row.addWidget(locate_btn)
        btn_row.addWidget(click_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)
        root.addWidget(self._last_result)
        root.addWidget(self._status)
        root.addStretch()

    def _collect_inputs(self):
        description = self._description.text().strip()
        if not description:
            self._status.setText(_t("vlm_desc_required"))
            return None
        model = self._model.text().strip() or None
        return description, model

    def _on_locate(self) -> None:
        inputs = self._collect_inputs()
        if inputs is None:
            return
        description, model = inputs
        try:
            coords = locate_by_description(description, model=model)
        except VLMNotAvailableError as error:
            QMessageBox.warning(self, _t("vlm_locate"), str(error))
            return
        except (OSError, ValueError, RuntimeError) as error:
            self._status.setText(f"{_t('vlm_error')}: {error}")
            return
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
        try:
            ok = click_by_description(description, model=model)
        except VLMNotAvailableError as error:
            QMessageBox.warning(self, _t("vlm_click"), str(error))
            return
        except (OSError, ValueError, RuntimeError) as error:
            self._status.setText(f"{_t('vlm_error')}: {error}")
            return
        self._status.setText(_t("vlm_ok") if ok else _t("vlm_not_found"))
