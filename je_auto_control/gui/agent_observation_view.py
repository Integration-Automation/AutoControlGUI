"""Read-only scoped controls and a one-to-one pixel preview for managed task requests."""
from __future__ import annotations

from typing import Any
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QLabel, QScrollArea, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.images import observation_image_bytes


class _Image(QLabel):
    picked = Signal(object)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Offer rendered image pixels without dispatching input or scaling coordinates."""
        x, y = math.floor(event.position().x()), math.floor(event.position().y())
        pixmap = self.pixmap()
        if event.button() == Qt.MouseButton.LeftButton and not pixmap.isNull():
            if 0 <= x < pixmap.width() and 0 <= y < pixmap.height():
                self.picked.emit({"image_point": [x, y]})
                event.accept()
                return
        super().mousePressEvent(event)


class AgentObservationView(QWidget):
    """Present one observation; selections only propose a reference to its immutable identifier."""

    picked = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.observation_id = ""
        self._indices: list[int] = []
        self._elements = QTableWidget(0, 4)
        self._elements.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._elements.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._elements.cellClicked.connect(self._pick_element)
        self._image = _Image()
        self._image.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._image.picked.connect(self.picked.emit)
        self._notice = QLabel()
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setWidget(self._image)
        layout = QVBoxLayout(self)
        layout.addWidget(self._elements)
        layout.addWidget(self._notice)
        layout.addWidget(scroll)
        self.clear()
        self.retranslate()

    def retranslate(self) -> None:
        """Translate columns without obtaining a new observation."""
        self._elements.setHorizontalHeaderLabels([language_wrapper.translate("agent_element_" + name, name)
                                                   for name in ("index", "name", "role", "bounds")])

    def clear(self) -> None:
        """Discard all frame-local selections and pixels on task changes or action dispatch."""
        self.observation_id = ""
        self._indices.clear()
        self._elements.setRowCount(0)
        self._image.setPixmap(QPixmap())
        self._image.setFixedSize(1, 1)
        self._notice.clear()

    def present(self, observation: dict[str, Any]) -> None:
        """Display bounded elements and validate the strict-masked JPEG before Qt decodes it."""
        self.clear()
        identifier, data = observation.get("observation_id"), observation.get("data")
        if not isinstance(identifier, str) or not identifier or not isinstance(data, dict):
            raise AgentTaskError("observation preview requires an identifier and data")
        self.observation_id = identifier
        elements = data.get("elements", [])
        if not isinstance(elements, list) or len(elements) > 10000:
            raise AgentTaskError("observation preview elements exceed their bound")
        self._present_elements(elements)
        image = data.get("image")
        if isinstance(image, dict):
            self._present_image(image)

    def _present_elements(self, elements: list) -> None:
        for index, element in enumerate(elements):
            if not isinstance(element, dict) or element.get("index", index) != index:
                raise AgentTaskError("observation preview element index is ambiguous")
            self._indices.append(index)
            self._elements.insertRow(index)
            for column, name in enumerate(("index", "name", "role", "bounds")):
                value = index if name == "index" else element.get(name, "")
                if name == "bounds" and "selector" in element:
                    value = {"selector": element["selector"], "frame": element.get("frame", "")}
                self._elements.setItem(index, column, QTableWidgetItem(str(value)))

    def _present_image(self, image: dict) -> None:
        try:
            pixels = observation_image_bytes(image)
            pixmap = QPixmap()
            if not pixmap.loadFromData(pixels, "JPEG"):
                raise AgentTaskError("observation preview image could not be decoded")
            pixmap.setDevicePixelRatio(1.0)
            self._image.setPixmap(pixmap)
            self._image.setFixedSize(pixmap.size())
        except AgentTaskError as error:
            self._notice.setText(str(error))

    def _pick_element(self, row: int, _column: int) -> None:
        if self.observation_id and 0 <= row < len(self._indices):
            self.picked.emit({"element_index": self._indices[row]})
