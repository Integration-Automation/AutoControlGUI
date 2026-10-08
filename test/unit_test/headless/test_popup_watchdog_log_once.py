"""A watchdog rule that keeps failing is logged once, not once per poll.

A rule whose owner was removed or demoted is refused on every poll -- once a
second by default -- and each refusal wrote an info line, for as long as the
process lived. The same was true of a matcher that raises every time. A rule
now reports a failure when it starts, when it changes, and when it stops.
"""
import logging

import pytest

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.rbac import (
    USERS_ENV, Role, UserStore, authorization_scope, resolve_token,
)
from je_auto_control.utils.watchdog.popup_watchdog import PopupWatchdog, WatchdogRule


@pytest.fixture(autouse=True)
def _no_ambient_rbac(monkeypatch):
    monkeypatch.delenv(USERS_ENV, raising=False)


@pytest.fixture()
def users(tmp_path):
    store = UserStore(tmp_path / "users.json")
    store.tokens = {role: store.add_user(user_id=f"{role}-user", display_name=role, role=role)
                    for role in Role.all()}
    return store


@pytest.fixture()
def lines(caplog):
    """The watchdog's log lines, read lazily."""
    caplog.set_level(logging.DEBUG, logger=autocontrol_logger.name)

    def read():
        return [record.getMessage() for record in caplog.records
                if "popup watchdog rule" in record.getMessage()]
    return read


def _owned_rule(users, watchdog, name="popup"):
    hits = []
    with authorization_scope(resolve_token(users, users.tokens[Role.OPERATOR])):
        watchdog.add_rule(WatchdogRule(name, matcher=lambda: True,
                                       action=lambda: hits.append(name)))
    return hits


def test_a_refused_owner_is_logged_once_however_often_it_is_polled(users, lines):
    watchdog = PopupWatchdog()
    hits = _owned_rule(users, watchdog)
    users.remove_user("operator-user")
    for _poll in range(25):
        assert watchdog.check_once() == 0
    assert hits == []
    assert len(lines()) == 1 and "no longer in the user store" in lines()[0]


def test_a_changed_refusal_is_logged_again(users, lines):
    watchdog = PopupWatchdog()
    _owned_rule(users, watchdog)
    users.set_role("operator-user", Role.VIEWER)
    for _poll in range(5):
        watchdog.check_once()
    users.remove_user("operator-user")
    for _poll in range(5):
        watchdog.check_once()
    assert len(lines()) == 2
    assert "drive_input" in lines()[0] and "no longer in the user store" in lines()[1]


def test_recovery_is_logged_once_and_a_later_refusal_is_reported_again(users, lines):
    watchdog = PopupWatchdog()
    hits = _owned_rule(users, watchdog)
    users.set_role("operator-user", Role.VIEWER)
    for _poll in range(3):
        watchdog.check_once()
    users.set_role("operator-user", Role.OPERATOR)
    for _poll in range(3):
        assert watchdog.check_once() == 1
    users.set_role("operator-user", Role.VIEWER)
    for _poll in range(3):
        watchdog.check_once()
    assert len(hits) == 3
    assert [("recovered" in line) for line in lines()] == [False, True, False]


def test_each_rule_keeps_its_own_state(users, lines):
    watchdog = PopupWatchdog()
    _owned_rule(users, watchdog, "first")
    _owned_rule(users, watchdog, "second")
    users.remove_user("operator-user")
    for _poll in range(4):
        watchdog.check_once()
    assert len(lines()) == 2
    assert "'first'" in lines()[0] and "'second'" in lines()[1]


def test_a_matcher_that_raises_every_poll_is_logged_once(lines):
    watchdog = PopupWatchdog()

    def broken():
        raise RuntimeError("no display")
    watchdog.add_rule(WatchdogRule("broken", matcher=broken, action=lambda: None))
    for _poll in range(10):
        assert watchdog.check_once() == 0
    assert len(lines()) == 1 and "no display" in lines()[0]


def test_a_rule_that_never_fails_logs_nothing(lines):
    watchdog = PopupWatchdog()
    watchdog.add_rule(WatchdogRule("quiet", matcher=lambda: False, action=lambda: None))
    for _poll in range(5):
        watchdog.check_once()
    assert lines() == []
