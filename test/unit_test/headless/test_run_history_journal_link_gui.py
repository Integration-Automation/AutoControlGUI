"""The Run History detail names the journal run of the selected row."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.gui import run_history_tab  # noqa: E402
from je_auto_control.utils.run_history.history_store import HistoryStore  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_detail_shows_the_journal_run_only_for_a_linked_row(qapp, monkeypatch):
    store = HistoryStore()
    store.start_run("manual", "plain", "plain.json", started_at=1.0)
    store.start_run("manual", "linked", "linked.json", started_at=2.0,
                    journal_path="journal.jsonl", journal_run_id="run-77")
    monkeypatch.setattr(run_history_tab, "default_history_store", store)
    tab = run_history_tab.RunHistoryTab()
    try:
        tab._timer.stop()
        tab._table.selectRow(0)
        caption = tab._thumb_caption.text()
        assert "run-77" in caption and "journal.jsonl" in caption
        tab._table.selectRow(1)
        assert "run-77" not in tab._thumb_caption.text()
    finally:
        tab.deleteLater()
