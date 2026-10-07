"""GUI smoke tests for the B-group tabs (a11y audit / matrix / media)."""
import os
import time
from threading import Event

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.gui.a11y_audit_tab import A11yAuditTab  # noqa: E402
from je_auto_control.gui.device_matrix_tab import DeviceMatrixTab  # noqa: E402
from je_auto_control.gui.media_checks_tab import MediaChecksTab  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_a11y_audit_tab_contrast(app):
    tab = A11yAuditTab()
    tab._fg.setText("0,0,0")
    tab._bg.setText("255,255,255")
    tab._on_contrast()
    assert "21" in tab._summary.text()


def test_device_matrix_tab_runs(app):
    tab = DeviceMatrixTab()
    tab._devices.setPlainText('[{"platform":"android","serial":"a"}]')
    tab._actions.setPlainText(
        '[["AC_set_var", {"name":"id","value":"${device.serial}"}]]',
    )
    tab._on_run()
    deadline = time.monotonic() + 5
    while tab._worker is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert tab._table.rowCount() == 1
    assert "1" in tab._summary.text()


def test_matrix_run_leaves_gui_responsive(app, monkeypatch):
    import je_auto_control as ac
    entered, release = Event(), Event()

    def run(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return ac.MatrixReport([ac.DeviceResult('left', 'android', True)])

    monkeypatch.setattr(ac, 'run_on_devices', run)
    tab = DeviceMatrixTab()
    tab._devices.setPlainText('[{"platform":"android","serial":"left"}]')
    try:
        tab._on_run()
        assert entered.wait(5)
        tab._on_probe()
        assert 'capabilities' in tab._metadata.toPlainText()
        assert tab._worker is not None
    finally:
        release.set()
        deadline = time.monotonic() + 5
        while tab._worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        tab.deleteLater()


def test_media_checks_tab_instantiates(app):
    tab = MediaChecksTab()
    assert tab._video_threshold.value() == pytest.approx(1.0)
