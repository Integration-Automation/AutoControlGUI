"""Screenshot / pixel-probe tab builder (extracted mixin)."""
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QTextEdit, QVBoxLayout, QWidget,
)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.gui.selector import open_region_selector
from je_auto_control.wrapper.auto_control_screen import screen_size, screenshot, get_pixel


def _t(key: str) -> str:
    """language_wrapper shorthand"""
    return language_wrapper.translate(key, key)


class ScreenshotTabMixin:
    """Provides the screenshot tab builder/handlers.

    Host widget must expose the ``TranslatableMixin`` API (``self._tr(...)``,
    ``self._translate(...)``) so every label registers for live language
    switching.
    """

    def _build_screenshot_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout()

        # Screen size (read via Actions menu -> Get Screen Size)
        size_group = self._tr(QGroupBox(), "screen_size_label")
        sg = QHBoxLayout()
        self.screen_size_label = QLabel("--")
        sg.addWidget(self.screen_size_label)
        size_group.setLayout(sg)
        layout.addWidget(size_group)

        # Screenshot inputs; capture runs from the Actions menu.
        ss_group = self._tr(QGroupBox(), "take_screenshot")
        ss_grid = QGridLayout()
        ss_grid.addWidget(self._tr(QLabel(), "file_path_label"), 0, 0)
        self.ss_path_input = QLineEdit()
        ss_grid.addWidget(self.ss_path_input, 0, 1)

        ss_grid.addWidget(self._tr(QLabel(), "region_label"), 1, 0)
        self.ss_region_input = QLineEdit()
        self.ss_region_input.setPlaceholderText("0, 0, 800, 600")
        ss_grid.addWidget(self.ss_region_input, 1, 1)
        ss_group.setLayout(ss_grid)
        layout.addWidget(ss_group)

        # Pixel probe inputs; lookup runs from the Actions menu.
        px_group = self._tr(QGroupBox(), "get_pixel_label")
        px_grid = QGridLayout()
        px_grid.addWidget(self._tr(QLabel(), "pixel_x"), 0, 0)
        self.pixel_x_input = QLineEdit("0")
        self.pixel_x_input.setValidator(QIntValidator())
        px_grid.addWidget(self.pixel_x_input, 0, 1)
        px_grid.addWidget(self._tr(QLabel(), "pixel_y"), 0, 2)
        self.pixel_y_input = QLineEdit("0")
        self.pixel_y_input.setValidator(QIntValidator())
        px_grid.addWidget(self.pixel_y_input, 0, 3)
        self.pixel_result_label = QLabel()
        self._pixel_result_suffix = " --"
        self.pixel_result_label.setText(
            self._translate("pixel_result") + self._pixel_result_suffix,
        )
        px_grid.addWidget(self.pixel_result_label, 1, 0, 1, 4)
        px_group.setLayout(px_grid)
        layout.addWidget(px_group)

        self.ss_result_text = QTextEdit()
        self.ss_result_text.setReadOnly(True)
        self.ss_result_text.setMaximumHeight(100)
        layout.addWidget(self.ss_result_text)
        layout.addStretch()
        tab.setLayout(layout)
        return tab

    def _get_screen_size(self):
        try:
            w, h = screen_size()
            self.screen_size_label.setText(f"{w} x {h}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            QMessageBox.warning(self, "Error", str(error))

    def _browse_ss_path(self):
        path, _ = QFileDialog.getSaveFileName(self, _t("save_screenshot"), "", "PNG (*.png);;All (*)")
        if path:
            self.ss_path_input.setText(path)

    def _pick_ss_region(self):
        region = open_region_selector(self)
        if region is None:
            return
        x, y, w, h = region
        self.ss_region_input.setText(f"{x}, {y}, {x + w}, {y + h}")

    def _take_screenshot(self):
        try:
            path = self.ss_path_input.text() or None
            region_text = self.ss_region_input.text().strip()
            region = None
            if region_text:
                region = [int(x.strip()) for x in region_text.split(",")]
            screenshot(file_path=path, screen_region=region)
            self.ss_result_text.setText(f"Screenshot saved: {path or '(not saved)'}")
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.ss_result_text.setText(f"Error: {error}")

    def _get_pixel_color(self):
        try:
            x = int(self.pixel_x_input.text())
            y = int(self.pixel_y_input.text())
            color = get_pixel(x, y)
            self._pixel_result_suffix = f" {color}"
            self.pixel_result_label.setText(
                self._translate("pixel_result") + self._pixel_result_suffix,
            )
        except (OSError, ValueError, TypeError, RuntimeError) as error:
            self.pixel_result_label.setText(f"Error: {error}")

    def _screenshot_retranslate(self) -> None:
        if hasattr(self, "pixel_result_label"):
            self.pixel_result_label.setText(
                self._translate("pixel_result") + self._pixel_result_suffix,
            )
