"""A save through another handle on the same file is seen, even within one clock tick.

``refresh()`` compared the file's ``(mtime, size)``. A rotated token has the
length of the old one, so two saves in the same tick looked alike: the MCP
admin tools save through a store of their own, and the server's store went on
accepting the token just rotated away.
"""
from je_auto_control.utils.rbac import users as users_module
from je_auto_control.utils.rbac.users import Role, UserAuthError, UserStore

import pytest


@pytest.fixture
def frozen_clock(monkeypatch):
    """Every stat of the file reads the same, as two saves within one tick do."""
    monkeypatch.setattr(UserStore, "_stamp", lambda self: (1, 1))


def test_a_rotation_through_another_handle_retires_the_old_token(tmp_path, frozen_clock):
    path = tmp_path / "users.json"
    server = UserStore(path)
    old = server.add_user(user_id="dave", display_name="Dave", role=Role.VIEWER)
    admin = UserStore(path)
    new = admin.rotate_token("dave")
    assert server.refresh() is True
    with pytest.raises(UserAuthError):
        server.authenticate(old)
    assert server.authenticate(new).user_id == "dave"


def test_a_role_change_through_another_handle_is_seen(tmp_path, frozen_clock):
    path = tmp_path / "users.json"
    server = UserStore(path)
    server.add_user(user_id="dave", display_name="Dave", role=Role.VIEWER)
    UserStore(path).set_role("dave", Role.OPERATOR)
    server.refresh()
    assert server.get("dave").role == Role.OPERATOR


def test_nothing_changed_reads_nothing(tmp_path, frozen_clock, monkeypatch):
    server = UserStore(tmp_path / "users.json")
    server.add_user(user_id="dave", display_name="Dave", role=Role.VIEWER)
    assert server.refresh() is False


def test_a_store_on_another_file_is_not_disturbed(tmp_path, frozen_clock):
    one = UserStore(tmp_path / "one.json")
    one.add_user(user_id="dave", display_name="Dave", role=Role.VIEWER)
    UserStore(tmp_path / "two.json").add_user(user_id="erin", display_name="Erin", role=Role.VIEWER)
    assert one.refresh() is False
    assert users_module._saves_of(users_module._saves_key(tmp_path / "one.json")) == 1
