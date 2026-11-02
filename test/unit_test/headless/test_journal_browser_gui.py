"""Offscreen journal browsing preserves snapshots, authority and owner lifetimes."""
import threading
import time

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QPushButton

import je_auto_control as ac
from je_auto_control.gui.journal_browser import JournalBrowser
from je_auto_control.gui.journal_browser_worker import JournalReadRequest, JournalReadWorker
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.run_history.history_store import JournalLink


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def browser(app):
    widget = JournalBrowser()
    yield widget
    widget.cancel()
    if widget._handle is not None:
        widget._handle.wait(5)
    widget.deleteLater()
    app.processEvents()


def _until(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


def _journal(path, run_id="chosen"):
    ac.execute_journal_run([["AC_set_var", {"name": "x", "value": "safe"}]], path,
                           options=ac.JournalRunOptions(run_id=run_id))


@pytest.mark.parametrize("next_action", ["viewer", "close"])
def test_queued_source_retains_caller_authority_and_obeys_close(browser, app, monkeypatch, next_action):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def inspect(path, **_kwargs):
        calls.append(path)
        entered.set()
        if not release.wait(5):
            raise RuntimeError("controlled reader was not released")
        return []

    monkeypatch.setattr("je_auto_control.gui.journal_browser_worker.inspect_journal", inspect)
    browser._path.setText("old.jsonl")
    try:
        browser.read()
        assert entered.wait(2)
        if next_action == "viewer":
            with authorization_scope(AuthorizationContext("reader", Role.VIEWER)):
                browser.open_source("new.jsonl", "run", "step")
        else:
            browser.open_source("new.jsonl", "run", "step")
            browser.close()
    finally:
        release.set()
    _until(app, lambda: browser._handle is None)
    assert calls == ["old.jsonl"] and browser._events == []
    if next_action == "viewer":
        assert browser._status_key == "journal_error"


def test_browser_has_only_inputs_and_views_until_an_action(browser):
    assert browser.findChildren(QPushButton) == []
    assert browser._handle is None and browser._table.rowCount() == 0
    assert browser._limit.minimum() == 1 and browser._limit.maximum() == 10000
    assert browser._limit.value() == 100


def test_real_read_keeps_lifecycle_snapshots_and_source(browser, app, tmp_path):
    path = tmp_path / "events.jsonl"
    _journal(path)
    original = path.read_bytes()
    browser._path.setText(str(path))
    browser.read()
    _until(app, lambda: browser._handle is None)
    assert browser._table.rowCount() == 2
    assert [row["status"] for row in browser._events] == ["incomplete", "ok"]
    browser._table.selectRow(1)
    assert '"run_id": "chosen"' in browser._details.toPlainText()
    assert path.read_bytes() == original


def test_links_select_run_without_automatic_file_io(browser, app, tmp_path):
    path = tmp_path / "events.jsonl"
    _journal(path, "one")
    _journal(path, "two")
    browser.set_links([JournalLink(1, str(path), "one"), JournalLink(1, str(path), "two")])
    assert browser._handle is None and browser._table.rowCount() == 0
    browser._links.setCurrentIndex(2)
    assert browser._run_id.text() == "two"
    browser._limit.setValue(1)
    browser.read()
    _until(app, lambda: browser._handle is None)
    assert len(browser._events) == 1 and browser._events[0]["run_id"] == "two"
    assert browser._events[0]["status"] == "incomplete"


def test_precancelled_worker_does_not_open_input(app, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("cancelled worker opened a file")
    monkeypatch.setattr("je_auto_control.gui.journal_browser_worker.inspect_journal", forbidden)
    worker = JournalReadWorker(JournalReadRequest(1, "unused", None, 100))
    outcomes = []
    worker.finished.connect(outcomes.append)
    worker.request_stop()
    worker.run()
    assert outcomes[0].status == "cancelled" and outcomes[0].events == []
    worker.deleteLater()


def test_worker_rechecks_captured_viewer_authority(app, monkeypatch):
    calls = []
    monkeypatch.setattr("je_auto_control.gui.journal_browser_worker.inspect_journal", lambda *a, **k: calls.append(1))
    with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
        worker = JournalReadWorker(JournalReadRequest(1, "unused", None, 100))
    outcomes = []
    worker.finished.connect(outcomes.append)
    worker.run()
    assert outcomes[0].status == "error" and calls == []
    worker.deleteLater()


def test_worker_retains_enclosing_path_policy(app, tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    with ac.journal_scope(ac.ActionJournal(allowed / "outer.jsonl"), path_policy=ac.PathPolicy([allowed])):
        worker = JournalReadWorker(JournalReadRequest(1, str(tmp_path / "outside.jsonl"), None, 100))
    outcomes = []
    worker.finished.connect(outcomes.append)
    worker.run()
    assert outcomes[0].status == "error" and "PathNotAllowedError" in outcomes[0].error
    worker.deleteLater()


def test_worker_progress_cancels_between_records(app, monkeypatch):
    scanned = []
    def inspect(path, **kwargs):
        for count in range(1, 201):
            scanned.append(count)
            kwargs["observer"](count)
        return []
    monkeypatch.setattr("je_auto_control.gui.journal_browser_worker.inspect_journal", inspect)
    worker = JournalReadWorker(JournalReadRequest(1, "unused", None, 100))
    worker.progress.connect(lambda request, count: worker.request_stop() if count == 100 else None)
    outcomes = []
    worker.finished.connect(outcomes.append)
    worker.run()
    assert outcomes[0].status == "cancelled" and max(scanned) <= 101
    worker.deleteLater()


def _blocked_reader(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def inspect(path, **kwargs):
        entered.set()
        assert release.wait(5)
        kwargs["observer"](1)
        return [{"sequence": 1, "run_id": "old", "status": "ok", "command": "AC_set_var"}]
    monkeypatch.setattr("je_auto_control.gui.journal_browser_worker.inspect_journal", inspect)
    return entered, release


def test_cancel_does_not_block_gui(browser, app, monkeypatch):
    entered, release = _blocked_reader(monkeypatch)
    browser._path.setText("unused")
    browser.read()
    try:
        assert entered.wait(2)
        browser.cancel()
        assert browser._handle.isRunning()
    finally:
        release.set()
    _until(app, lambda: browser._handle is None)
    assert browser._events == [] and browser._status_key == "journal_cancelled"


def test_changing_target_discards_stale_completion(browser, app, monkeypatch):
    entered, release = _blocked_reader(monkeypatch)
    browser._path.setText("old")
    browser.read()
    try:
        assert entered.wait(2)
        browser.set_links([JournalLink(7, "new", "new-run")])
    finally:
        release.set()
    _until(app, lambda: browser._handle is None)
    assert browser._path.text() == "new" and browser._run_id.text() == "new-run"
    assert browser._events == [] and browser._status_key == "journal_idle"


def test_destroying_owner_requests_stop_and_drops_late_results(app, monkeypatch):
    entered, release = _blocked_reader(monkeypatch)
    widget = JournalBrowser()
    widget._path.setText("unused")
    widget.read()
    handle, worker = widget._handle, widget._worker
    try:
        assert entered.wait(2)
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert worker._stop.is_set()
    finally:
        release.set()
        assert handle.wait(5)
    app.processEvents()


def test_viewer_is_refused_before_worker_creation(browser):
    browser._path.setText("private.jsonl")
    with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
        browser.read()
    assert browser._handle is None and browser._status_key == "journal_error"


def test_corrupt_read_clears_previous_snapshots(browser, app, tmp_path):
    path = tmp_path / "events.jsonl"
    _journal(path)
    browser._path.setText(str(path))
    browser.read()
    _until(app, lambda: browser._handle is None)
    assert browser._events
    path.write_text("invalid\n", encoding="utf-8")
    browser.read()
    _until(app, lambda: browser._handle is None)
    assert browser._events == [] and browser._table.rowCount() == 0
    assert browser._status_key == "journal_error"


def test_history_menu_loads_links_without_reading(app, monkeypatch, tmp_path):
    from je_auto_control.gui import run_history_tab as history_module
    store = ac.HistoryStore(tmp_path / "history.sqlite")
    run = store.start_run("manual", "test", "script")
    store.attach_journal(run, str(tmp_path / "events.jsonl"), "chosen")
    monkeypatch.setattr(history_module, "default_history_store", store)
    tab = history_module.RunHistoryTab()
    try:
        tab._timer.stop()
        tab._table.selectRow(0)
        actions = dict(tab.menu_actions())
        assert "journal_selected_run" in actions and "journal_read" in actions and "journal_cancel" in actions
        actions["journal_selected_run"]()
        assert tab._journal._path.text() == str(tmp_path / "events.jsonl")
        assert tab._journal._run_id.text() == "chosen" and tab._journal._handle is None
    finally:
        tab.deleteLater()
        store.close()


def test_close_requests_cancellation_before_deferred_deletion(browser, app, monkeypatch):
    entered, release = _blocked_reader(monkeypatch)
    browser._path.setText("unused")
    browser.read()
    try:
        assert entered.wait(2)
        browser.close()
        assert browser._worker._stop.is_set()
    finally:
        release.set()
    _until(app, lambda: browser._handle is None)
    assert browser._status_key == "journal_cancelled"


@pytest.mark.parametrize("change", ["remove", "demote"])
def test_worker_refreshes_store_backed_owner_before_io(app, monkeypatch, tmp_path, change):
    from je_auto_control.utils.rbac.authorization import resolve_token
    from je_auto_control.utils.rbac.users import UserStore
    store = UserStore(tmp_path / "users.json")
    token = store.add_user(user_id="owner", display_name="Owner", role=Role.ADMIN)
    with authorization_scope(resolve_token(store, token)):
        worker = JournalReadWorker(JournalReadRequest(1, "private", None, 100))
    if change == "remove":
        UserStore(store.path).remove_user("owner")
    else:
        UserStore(store.path).set_role("owner", Role.VIEWER)
    def forbidden(*args, **kwargs):
        pytest.fail("revoked owner read private data")
    monkeypatch.setattr("je_auto_control.gui.journal_browser_worker.inspect_journal", forbidden)
    outcomes = []
    worker.finished.connect(outcomes.append)
    worker.run()
    assert outcomes[0].status == "error" and outcomes[0].events == []
    worker.deleteLater()


def test_history_retranslates_browser_and_preserves_state(app, monkeypatch, tmp_path):
    from je_auto_control.gui import run_history_tab as history_module
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
    store = ac.HistoryStore(tmp_path / "history.sqlite")
    monkeypatch.setattr(history_module, "default_history_store", store)
    tab = history_module.RunHistoryTab()
    old_language = language_wrapper.language
    try:
        tab._timer.stop()
        tab._journal._set_status("journal_done", "2")
        language_wrapper.reset_language("Japanese")
        tab.retranslate()
        assert tab._journal._status.text() == "2 件のスナップショットを表示。"
        assert tab._journal._table.horizontalHeaderItem(1).text() == "状態"
    finally:
        language_wrapper.reset_language(old_language)
        tab.deleteLater()
        store.close()


def test_history_viewer_cannot_resolve_private_links(app, monkeypatch, tmp_path):
    from je_auto_control.gui import run_history_tab as history_module
    store = ac.HistoryStore(tmp_path / "history.sqlite")
    store.start_run("manual", "test", "script")
    monkeypatch.setattr(history_module, "default_history_store", store)
    def forbidden(*args, **kwargs):
        pytest.fail("viewer resolved private provenance")
    monkeypatch.setattr(store, "journals_for_run", forbidden)
    tab = history_module.RunHistoryTab()
    try:
        tab._timer.stop()
        tab._table.selectRow(0)
        with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
            dict(tab.menu_actions())["journal_selected_run"]()
        assert tab._journal._status_key == "journal_error"
        assert tab._journal._links.count() == 1
    finally:
        tab.deleteLater()
        store.close()


def test_browse_viewer_is_refused_before_file_dialog(browser, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("viewer opened private file picker")
    monkeypatch.setattr("je_auto_control.gui.journal_browser.QFileDialog.getOpenFileName", forbidden)
    with authorization_scope(AuthorizationContext("viewer", Role.VIEWER)):
        browser.browse()
    assert browser._status_key == "journal_error" and browser._handle is None


def test_worker_masks_errors_in_active_captured_context(app, monkeypatch):
    from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
    secret = "private-journal-marker"
    def fail(*args, **kwargs):
        raise ValueError(secret)
    monkeypatch.setattr("je_auto_control.gui.journal_browser_worker.inspect_journal", fail)
    outcomes = []
    with secret_log_scope():
        remember_secret(secret)
        worker = JournalReadWorker(JournalReadRequest(1, "unused", None, 100))
        worker.finished.connect(outcomes.append)
        worker.run()
    assert outcomes[0].status == "error" and secret not in outcomes[0].error
    assert "***" in outcomes[0].error
    worker.deleteLater()


def test_error_details_are_plain_text(browser):
    from PySide6.QtCore import Qt
    browser.report_error("<b>literal</b>")
    assert browser._status.textFormat() == Qt.TextFormat.PlainText
    assert "<b>literal</b>" in browser._status.text()


def test_progress_is_delivered_on_gui_thread(browser, app, monkeypatch):
    gui_ident = threading.get_ident()
    calls = []
    original = browser._set_status
    def status(key, value=""):
        calls.append(threading.get_ident())
        original(key, value)
    monkeypatch.setattr(browser, "_set_status", status)
    def inspect(path, **kwargs):
        kwargs["observer"](100)
        return []
    monkeypatch.setattr("je_auto_control.gui.journal_browser_worker.inspect_journal", inspect)
    browser._path.setText("unused")
    browser.read()
    _until(app, lambda: browser._handle is None)
    assert calls and set(calls) == {gui_ident}


def test_history_close_cancels_its_child_reader(app, monkeypatch, tmp_path):
    from je_auto_control.gui import run_history_tab as history_module
    entered, release = _blocked_reader(monkeypatch)
    store = ac.HistoryStore(tmp_path / "history.sqlite")
    monkeypatch.setattr(history_module, "default_history_store", store)
    tab = history_module.RunHistoryTab()
    tab._journal._path.setText("unused")
    tab._journal.read()
    handle = tab._journal._handle
    try:
        assert entered.wait(2)
        tab.close()
        assert tab._journal._worker._stop.is_set() and not tab._timer.isActive()
    finally:
        release.set()
        assert handle.wait(5)
        app.processEvents()
        tab.deleteLater()
        store.close()


def test_lookup_error_invalidates_an_older_read(browser, app, monkeypatch):
    entered, release = _blocked_reader(monkeypatch)
    browser._path.setText("old")
    browser.read()
    try:
        assert entered.wait(2)
        browser.report_error("new history lookup failed")
    finally:
        release.set()
    _until(app, lambda: browser._handle is None)
    assert browser._events == [] and browser._status_key == "journal_error"
    assert "new history lookup failed" in browser._status.text()
