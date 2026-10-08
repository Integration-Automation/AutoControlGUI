"""The REST API tab under RBAC: the real authentication state, and user management.

The tab showed the shared bearer token even when a user store was configured,
where the server refuses that token. It now says whose tokens are accepted,
and its users group adds, re-roles, rotates and removes users through the
same headless functions as ``AC_user_*``.

Offscreen Qt only; no window is shown, no dialog is opened and the clipboard
is not touched.
"""
import os

import pytest

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from je_auto_control.gui import rbac_users_panel  # noqa: E402
from je_auto_control.gui.language_wrapper import (  # noqa: E402
    english, japanese, simplified_chinese, traditional_chinese,
)
from je_auto_control.gui.rbac_users_panel import RbacUsersPanel  # noqa: E402
from je_auto_control.gui.rest_api_tab import RestApiTab  # noqa: E402
from je_auto_control.utils.rbac import USERS_ENV, Role, UserStore, admin  # noqa: E402
from je_auto_control.utils.rest_api.rest_registry import rest_api_registry  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    """No ambient RBAC, no audit row in the developer's database, no leftover server."""
    monkeypatch.delenv(USERS_ENV, raising=False)
    monkeypatch.setattr(admin, "_audit", lambda *_args: None)
    yield
    rest_api_registry.stop()


@pytest.fixture()
def tab(app):
    widget = RestApiTab()
    yield widget
    widget._timer.stop()
    widget.deleteLater()


def _t(key):
    """The string the GUI shows for ``key`` in whatever language is active."""
    return rbac_users_panel._t(key)


def _rows(panel):
    table = panel._table
    return [tuple(table.item(row, column).text() for column in range(3))
            for row in range(table.rowCount())]


def _fill(panel, user_id, role=Role.VIEWER, name=""):
    panel._id_input.setText(user_id)
    panel._name_input.setText(name)
    panel._role_input.setCurrentText(role)


# --- the tab shows how to authenticate --------------------------------------

def test_shared_token_mode_shows_the_token(tab):
    tab._port_input.setValue(0)
    tab._token_input.setText("shared-secret")
    tab._audit_check.setChecked(False)
    tab._on_start()
    assert tab._token_value.text() == "shared-secret"
    assert tab._shared_token == "shared-secret"
    assert tab._status_label.text() == _t("rest_running")
    tab._on_stop()
    assert tab._token_value.text() == "-" and tab._shared_token is None


def test_rbac_mode_names_the_user_store_instead_of_a_refused_token(tab, tmp_path):
    path = tmp_path / "users.json"
    token = UserStore(path).add_user(user_id="alice", display_name="Alice", role=Role.ADMIN)
    tab._users_panel._path_input.setText(str(path))
    tab._users_panel._enable_check.setChecked(True)
    tab._port_input.setValue(0)
    tab._token_input.setText("shared-secret")
    tab._audit_check.setChecked(False)
    tab._on_start()
    server = rest_api_registry.server
    assert server.user_store is not None and server.user_store.path == path.resolve()
    shown = tab._token_value.text()
    assert "shared-secret" not in shown and server.token not in shown and token not in shown
    assert str(path.resolve()) in shown
    assert tab._shared_token is None, "nothing for Copy token to hand out"
    assert tab._status_label.text() == _t("rest_running_rbac")


def test_the_user_store_is_used_only_when_ticked(tab, tmp_path):
    tab._users_panel._path_input.setText(str(tmp_path / "users.json"))
    tab._users_panel._enable_check.setChecked(False)
    tab._port_input.setValue(0)
    tab._audit_check.setChecked(False)
    tab._on_start()
    assert rest_api_registry.server.user_store is None
    assert tab._shared_token == rest_api_registry.server.token


def test_the_tab_offers_the_user_commands_in_its_menu(tab):
    keys = [key for key, _handler in tab.menu_actions()]
    assert keys[:6] == ["rest_start", "rest_stop", "rest_copy_url", "rest_copy_token",
                        "rest_config_export", "rest_config_import"]
    assert keys[6:] == ["rest_users_refresh", "rest_users_add", "rest_users_set_role",
                        "rest_users_rotate", "rest_users_remove", "rest_users_copy_token"]
    assert all(callable(handler) for _key, handler in tab.menu_actions())


# --- the users group --------------------------------------------------------

@pytest.fixture()
def panel(app, tmp_path):
    widget = RbacUsersPanel()
    widget._path_input.setText(str(tmp_path / "users.json"))
    yield widget
    widget.deleteLater()


def test_the_path_defaults_to_the_configured_store(app, tmp_path, monkeypatch):
    monkeypatch.setenv(USERS_ENV, str(tmp_path / "configured.json"))
    widget = RbacUsersPanel()
    assert widget.users_path() == str(tmp_path / "configured.json")
    assert widget._enable_check.isChecked() and widget.user_store() is not None
    widget.deleteLater()
    empty = RbacUsersPanel()
    empty._path_input.clear()
    assert empty.users_path() is None and empty.user_store() is None
    empty.refresh()
    assert empty._status_label.text() == _t("rest_users_no_store")
    empty.deleteLater()


def test_add_shows_the_token_once(panel, tmp_path):
    _fill(panel, "alice", Role.ADMIN, "Alice")
    panel._on_add()
    token = panel._token_value.text()
    assert UserStore(tmp_path / "users.json").authenticate(token).role == Role.ADMIN
    assert _rows(panel) == [("alice", "Alice", "admin")]
    assert token not in panel._status_label.text()
    panel.refresh()
    assert panel._token_value.text() == "", "gone after the next operation"
    assert _rows(panel) == [("alice", "Alice", "admin")]


def test_select_a_row_then_change_role_rotate_and_remove(panel, tmp_path, monkeypatch):
    store_path = tmp_path / "users.json"
    _fill(panel, "alice", Role.ADMIN)
    panel._on_add()
    _fill(panel, "bob", Role.VIEWER, "Bob")
    panel._on_add()
    first_token = panel._token_value.text()
    panel._id_input.clear()
    panel._table.selectRow(1)
    assert panel._id_input.text() == "bob" and panel._role_input.currentText() == "viewer"
    panel._role_input.setCurrentText(Role.OPERATOR)
    panel._on_set_role()
    assert _rows(panel)[1] == ("bob", "Bob", "operator")
    assert panel._token_value.text() == ""
    panel._on_rotate()
    rotated = panel._token_value.text()
    assert rotated and rotated != first_token
    assert UserStore(store_path).authenticate(rotated).user_id == "bob"
    answers = iter([QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes])
    monkeypatch.setattr(rbac_users_panel.QMessageBox, "question",
                        lambda *_args, **_kwargs: next(answers))
    panel._on_remove()
    assert len(_rows(panel)) == 2, "declined"
    panel._on_remove()
    assert _rows(panel) == [("alice", "alice", "admin")]


def test_errors_are_shown_in_the_panel_not_in_a_dialog(panel, monkeypatch):
    monkeypatch.setattr(rbac_users_panel.QMessageBox, "question",
                        lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes)
    panel._on_add()
    assert panel._status_label.text() == _t("rest_users_no_user")
    _fill(panel, "alice", Role.ADMIN)
    panel._on_add()
    panel._on_add()
    assert "already exists" in panel._status_label.text() and panel._token_value.text() == ""
    panel._on_remove()
    assert "only admin" in panel._status_label.text()
    _fill(panel, "nobody")
    panel._on_rotate()
    assert "unknown user_id" in panel._status_label.text()


def test_an_unreadable_store_is_reported(panel, tmp_path):
    (tmp_path / "users.json").write_text("not json", encoding="utf-8")
    panel.refresh()
    assert _rows(panel) == []
    _fill(panel, "alice", Role.ADMIN)
    panel._on_add()
    assert "unreadable" in panel._status_label.text()
    assert (tmp_path / "users.json").read_text(encoding="utf-8") == "not json"


# --- the strings exist in every language ------------------------------------

def test_every_new_key_is_translated_in_all_four_catalogues():
    catalogues = {
        "english": english.english_word_dict,
        "japanese": japanese.japanese_word_dict,
        "traditional_chinese": traditional_chinese.traditional_chinese_word_dict,
        "simplified_chinese": simplified_chinese.simplified_chinese_word_dict,
    }
    keys = [key for key in catalogues["english"]
            if key.startswith("rest_users_") or key in ("rest_token_rbac", "rest_running_rbac")]
    assert len(keys) == 24
    for language, words in catalogues.items():
        for key in keys:
            assert words.get(key), f"{language} lacks {key}"
    for words in catalogues.values():
        assert "{path}" in words["rest_token_rbac"] and "{user}" in words["rest_users_remove_confirm"]
        assert "{count}" in words["rest_users_count"] and "{path}" in words["rest_users_count"]
        assert "{user}" in words["rest_users_token_issued"]
