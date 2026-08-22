"""The 'Advanced' STUN/TURN group both WebRTC panels build.

Split out of ``webrtc_panel`` for two reasons at once. It is a shared widget
builder rather than part of either panel, and it *writes* the five edits it
creates back onto the panel it is given — a contract that has to be written
down somewhere, and could not be written down inside a file already sitting on
its line-count cap.

The panel argument is therefore a :class:`AdvancedGroupHost`: what the builder
reads (``_tr``, ``_on_hw_codec_changed``) and what it sets (the five widgets).
Imports ``PySide6`` — it is GUI-only by construction.
"""
from __future__ import annotations

from typing import Any, Protocol

from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QLabel, QLineEdit, QWidget,
)

from je_auto_control.gui.remote_desktop._helpers import _t
from je_auto_control.utils.remote_desktop import (
    active_hardware_codec, available_hardware_codecs,
)

DEFAULT_STUN = "stun:stun.l.google.com:19302"


class AdvancedGroupHost(Protocol):
    """A WebRTC panel, seen from the advanced group it hosts.

    ``_tr`` and ``_on_hw_codec_changed`` are read; the five widget
    attributes are *assigned* by :func:`build_advanced_group`, which is why
    this cannot be the plain ``TranslatableMixin`` the parameter used to
    name — that class has none of them.
    """

    _stun_edit: Any
    _turn_edit: Any
    _turn_user_edit: Any
    _turn_cred_edit: Any
    _hw_codec_combo: Any

    def _tr(self, widget: QWidget, key: str, setter: str = "") -> QWidget:
        """Register ``widget`` for live re-translation and return it."""

    def _on_hw_codec_changed(self) -> None:
        """React to the hardware-codec selection changing."""


def build_advanced_group(panel: AdvancedGroupHost,
                         include_hw_codec: bool = False) -> QGroupBox:
    """Shared 'Advanced' STUN/TURN (+ optional hw codec) group."""
    group = panel._tr(QGroupBox(), "rd_webrtc_advanced_group")
    grid = QGridLayout()
    grid.addWidget(panel._tr(QLabel(), "rd_webrtc_stun_label"), 0, 0)
    panel._stun_edit = QLineEdit(DEFAULT_STUN)
    grid.addWidget(panel._stun_edit, 0, 1, 1, 3)
    grid.addWidget(panel._tr(QLabel(), "rd_webrtc_turn_label"), 1, 0)
    panel._turn_edit = panel._tr(QLineEdit(), "rd_webrtc_turn_placeholder")
    grid.addWidget(panel._turn_edit, 1, 1, 1, 3)
    grid.addWidget(panel._tr(QLabel(), "rd_webrtc_turn_user_label"), 2, 0)
    panel._turn_user_edit = QLineEdit()
    grid.addWidget(panel._turn_user_edit, 2, 1)
    grid.addWidget(panel._tr(QLabel(), "rd_webrtc_turn_cred_label"), 2, 2)
    panel._turn_cred_edit = QLineEdit()
    panel._turn_cred_edit.setEchoMode(QLineEdit.EchoMode.Password)
    grid.addWidget(panel._turn_cred_edit, 2, 3)
    if include_hw_codec:
        _add_hw_codec_row(panel, grid)
    group.setLayout(grid)
    return group


def _add_hw_codec_row(panel: AdvancedGroupHost, grid: QGridLayout) -> None:
    """Add the hardware-codec picker, pre-selected to the active codec."""
    grid.addWidget(panel._tr(QLabel(), "rd_webrtc_hw_codec_label"), 3, 0)
    combo = QComboBox()
    panel._hw_codec_combo = combo
    combo.addItem(_t("rd_webrtc_hw_codec_off"), "")
    for name in available_hardware_codecs():
        combo.addItem(name, name)
    active = active_hardware_codec()
    if active:
        index = combo.findData(active)
        if index >= 0:
            combo.setCurrentIndex(index)
    combo.currentIndexChanged.connect(lambda _i: panel._on_hw_codec_changed())
    grid.addWidget(combo, 3, 1, 1, 3)


__all__ = ["DEFAULT_STUN", "AdvancedGroupHost", "build_advanced_group"]
