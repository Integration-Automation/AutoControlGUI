"""Image-detection tab builder (extracted mixin)."""
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QGridLayout, QLabel, QLineEdit, QMessageBox,
    QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.selector import crop_template_to_file
from je_auto_control.wrapper.auto_control_image import (
    locate_all_image, locate_image_center, locate_and_click,
)


def _t(key: str) -> str:
    """language_wrapper shorthand"""
    return language_wrapper.translate(key, key)


class ImageDetectTabMixin:
    """Provides the image-detection tab builder/handlers.

    Host widget must expose the ``TranslatableMixin`` API (``self._tr(...)``).
    ``_locate_click`` reuses the auto-click tab's ``mouse_button_combo`` when
    the host also mixes in :class:`AutoClickTabMixin`, falling back to the
    left button otherwise.
    """

    if TYPE_CHECKING:
        # Declared, never defined: the widget this mixin is mixed into owns
        # every one of these. The block is stripped at runtime, so nothing
        # here can shadow what the host actually binds.
        _tr: Callable[..., Any]

    def _build_image_detect_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        # Detection inputs; locate/crop commands run from the Actions menu.
        grid = QGridLayout()
        grid.addWidget(self._tr(QLabel(), "template_image"), 0, 0)
        self.img_path_input = QLineEdit()
        grid.addWidget(self.img_path_input, 0, 1)

        grid.addWidget(self._tr(QLabel(), "threshold_label"), 1, 0)
        self.threshold_input = QLineEdit("0.8")
        self.threshold_input.setValidator(QDoubleValidator(0.0, 1.0, 2))
        grid.addWidget(self.threshold_input, 1, 1)
        self.draw_check = self._tr(QCheckBox(), "draw_image_check")
        grid.addWidget(self.draw_check, 1, 2)

        layout.addLayout(grid)

        layout.addWidget(self._tr(QLabel(), "detection_result"))
        self.detect_result_text = QTextEdit()
        self.detect_result_text.setReadOnly(True)
        layout.addWidget(self.detect_result_text)
        tab.setLayout(layout)
        return tab

    def _browse_img(self):
        path, _ = QFileDialog.getOpenFileName(self, _t("template_image"), "", "Images (*.png *.jpg *.bmp);;All (*)")
        if path:
            self.img_path_input.setText(path)

    def _crop_template(self):
        save_path, _ = QFileDialog.getSaveFileName(
            self, _t("crop_template"), "", "PNG (*.png)"
        )
        if not save_path:
            return
        try:
            region = crop_template_to_file(save_path, self)
            if region is None:
                return
            self.img_path_input.setText(save_path)
            self.detect_result_text.setText(f"Template saved: {save_path} region={region}")
        except (OSError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _get_detect_params(self):
        path = self.img_path_input.text()
        if not path:
            raise ValueError("Template image path is empty")
        threshold = float(self.threshold_input.text() or "0.8")
        draw = self.draw_check.isChecked()
        return path, threshold, draw

    def _locate_image(self):
        try:
            path, th, draw = self._get_detect_params()
            result = locate_image_center(path, th, draw)
            self.detect_result_text.setText(f"Center: {result}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.detect_result_text.setText(f"Error: {error}")

    def _locate_all(self):
        try:
            path, th, draw = self._get_detect_params()
            result = locate_all_image(path, th, draw)
            self.detect_result_text.setText(f"Found {len(result)} matches:\n{result}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.detect_result_text.setText(f"Error: {error}")

    def _locate_click(self):
        try:
            path, th, draw = self._get_detect_params()
            btn = self.mouse_button_combo.currentText() if hasattr(self, "mouse_button_combo") else "mouse_left"
            result = locate_and_click(path, btn, th, draw)
            self.detect_result_text.setText(f"Clicked at: {result}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.detect_result_text.setText(f"Error: {error}")
