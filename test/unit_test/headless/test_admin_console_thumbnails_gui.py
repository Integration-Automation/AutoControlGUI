"""Phase 6.5 GUI: tests for the live-thumbnail grid in AdminConsoleTab."""
import os
from io import BytesIO
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402


def _png_bytes(width: int = 16, height: int = 16) -> bytes:
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(120, 200, 40))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def populated_admin_tab(qapp, tmp_path, monkeypatch):
    """An AdminConsoleTab pre-seeded with two hosts and a temp address book."""
    from je_auto_control.utils.admin.admin_client import AdminConsoleClient
    from je_auto_control.gui import admin_console_tab as tab_mod
    client = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
    client.add_host("alpha", "http://a.example", "tok-a")
    client.add_host("beta", "http://b.example", "tok-b")
    monkeypatch.setattr(
        tab_mod, "default_admin_console", lambda: client,
    )
    from je_auto_control.gui.admin_console_tab import AdminConsoleTab
    tab = AdminConsoleTab()
    yield tab, client
    tab.deleteLater()


def test_thumbnail_widget_present_and_default_interval(populated_admin_tab):
    tab, _ = populated_admin_tab
    assert tab._thumbnails is not None  # noqa: SLF001
    assert tab._thumb_interval.value() == 10  # noqa: SLF001  # default 10 s


def test_apply_thumbnails_paints_tiles(populated_admin_tab):
    tab, _ = populated_admin_tab
    png = _png_bytes()
    tab._apply_thumbnails({"alpha": png, "beta": png})  # noqa: SLF001
    assert tab._thumbnails.count() == 2  # noqa: SLF001
    # Each tile has the label as its text.
    labels = {
        tab._thumbnails.item(i).text()  # noqa: SLF001
        for i in range(tab._thumbnails.count())  # noqa: SLF001
    }
    assert labels == {"alpha", "beta"}


def test_apply_thumbnails_handles_none_payload(populated_admin_tab):
    """A host that failed (None) still gets a tile with no icon."""
    tab, _ = populated_admin_tab
    tab._apply_thumbnails(  # noqa: SLF001
        {"alpha": _png_bytes(), "beta": None},
    )
    assert tab._thumbnails.count() == 2  # noqa: SLF001
    # alpha has an icon, beta does not.
    alpha_icon = tab._thumbnails.item(0).icon()  # noqa: SLF001
    beta_icon = tab._thumbnails.item(1).icon()  # noqa: SLF001
    assert not alpha_icon.isNull()
    assert beta_icon.isNull()


def test_apply_thumbnails_handles_malformed_png(populated_admin_tab):
    """A non-PNG payload should not crash, just produce no icon."""
    tab, _ = populated_admin_tab
    tab._apply_thumbnails(  # noqa: SLF001
        {"alpha": b"not-a-real-png"},
    )
    assert tab._thumbnails.count() == 1  # noqa: SLF001
    assert tab._thumbnails.item(0).icon().isNull()  # noqa: SLF001


def test_thumb_interval_zero_stops_the_timer(populated_admin_tab):
    tab, _ = populated_admin_tab
    tab._thumb_interval.setValue(0)  # noqa: SLF001
    assert not tab._thumb_timer.isActive()  # noqa: SLF001
    tab._thumb_interval.setValue(15)  # noqa: SLF001
    assert tab._thumb_timer.isActive()  # noqa: SLF001
    assert tab._thumb_timer.interval() == 15_000  # noqa: SLF001


def test_thumbnail_worker_pulls_through_admin_client(populated_admin_tab):
    """The headless worker calls fetch_thumbnails and emits the result."""
    from je_auto_control.gui.admin_console_tab import _ThumbnailWorker
    tab, client = populated_admin_tab
    png = _png_bytes()
    captured = []
    with patch.object(
        client.__class__, "fetch_thumbnails",
        return_value={"alpha": png, "beta": None},
    ):
        worker = _ThumbnailWorker(client)
        worker.finished.connect(captured.append)
        worker.run()  # run synchronously — no QThread in this test
    assert captured == [{"alpha": png, "beta": None}]


def test_apply_thumbnails_from_worker_result(populated_admin_tab):
    """Feeding the worker's emitted dict to the tab paints both tiles."""
    tab, _ = populated_admin_tab
    png = _png_bytes()
    tab._apply_thumbnails({"alpha": png, "beta": None})  # noqa: SLF001
    assert tab._thumbnails.count() == 2  # noqa: SLF001
