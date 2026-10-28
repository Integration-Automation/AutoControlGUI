"""Missing optional codec helpers leave the background-built controls usable."""

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
pytest.importorskip("av")
pytest.importorskip("aiortc")

from PySide6.QtWidgets import QApplication, QComboBox, QLabel

from je_auto_control.gui.remote_desktop import advanced_group, webrtc_panel


@pytest.fixture(scope="module")
def qapp():
    """Keep Qt entirely offscreen for these widget checks."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize("missing", ["available_hardware_codecs", "active_hardware_codec", "both"])
def test_missing_codec_helpers_disable_picker(qapp, monkeypatch, missing):
    """A missing member prevents enumeration and leaves only the disabled off choice."""
    def unexpected_call():
        raise AssertionError("incomplete codec group must not be called")

    for name in ("available_hardware_codecs", "active_hardware_codec"):
        monkeypatch.setattr(advanced_group, name, None if missing in (name, "both") else unexpected_call)
    panel = SimpleNamespace(_tr=lambda widget, key: widget, _on_hw_codec_changed=lambda: None)
    group = advanced_group.build_advanced_group(panel, include_hw_codec=True)
    assert not panel._hw_codec_combo.isEnabled()
    assert panel._hw_codec_combo.count() == 1
    assert panel._hw_codec_combo.currentData() == ""
    group.close()


def test_available_codec_helpers_populate_and_select_picker(qapp, monkeypatch):
    """Available helpers retain the selected codec without opening hardware."""
    monkeypatch.setattr(advanced_group, "available_hardware_codecs", lambda: ["h264_nvenc", "h264_qsv"])
    monkeypatch.setattr(advanced_group, "active_hardware_codec", lambda: "h264_qsv")
    panel = SimpleNamespace(_tr=lambda widget, key: widget, _on_hw_codec_changed=lambda: None)
    group = advanced_group.build_advanced_group(panel, include_hw_codec=True)
    assert panel._hw_codec_combo.isEnabled()
    assert panel._hw_codec_combo.count() == 3
    assert panel._hw_codec_combo.currentData() == "h264_qsv"
    group.close()


@pytest.mark.parametrize("codec", ["", "h264_nvenc"])
def test_missing_codec_actions_report_failure(qapp, monkeypatch, codec):
    """A stale selection cannot call unavailable install or uninstall functions."""
    monkeypatch.setattr(webrtc_panel, "install_hardware_codec", None)
    monkeypatch.setattr(webrtc_panel, "uninstall_hardware_codec", None)
    combo = QComboBox()
    combo.addItem("selected", codec)
    label = QLabel()
    panel = SimpleNamespace(_hw_codec_combo=combo, _status_label=label)
    webrtc_panel._WebRTCHostPanel._on_hw_codec_changed(panel)
    expected = (webrtc_panel._t("rd_webrtc_hw_codec_failed").format(codec=codec)
                if codec else webrtc_panel._t("rd_webrtc_unavailable"))
    assert label.text() == expected
    combo.close()
    label.close()
