"""``hotkey`` / ``type_keyboard`` must never leave a key held down.

Both are "press, then release" with nothing protecting the gap. If any step
raises part-way, the keys already pressed stay pressed — on the user's real
keyboard. A stuck ``Ctrl`` or ``Alt`` silently changes the meaning of every
subsequent click and keystroke, and nothing on screen says why.

**Why ``finally`` and not a wider ``except``.** Both functions catch
``(OSError, RuntimeError, AttributeError, TypeError, ValueError)``, and
``press_keyboard_key`` / ``release_keyboard_key`` raise
``AutoControlKeyboardException`` — which derives from ``AutoControlException``
and is under *none* of those five. So the most likely failures (a key name the
table has no entry for, an unsupported platform, a backend error) never reach
that ``except`` at all. ``finally`` is the only exit path that always runs;
``test_the_except_tuple_cannot_catch_the_exception_these_raise`` pins that
premise, because the whole design rests on it.

Nothing here touches the real desktop: the low-level ``press_key`` /
``release_key`` are replaced with recorders.
"""
import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlKeyboardException,
)
from je_auto_control.wrapper import auto_control_keyboard as kb


class _Recorder:
    """Records press/release calls; can be told to fail on a chosen key."""

    def __init__(self, fail_press_on=None, fail_release_on=None,
                 release_failures=None, error=None, release_error=None):
        self.events: list[tuple[str, object]] = []
        self._fail_press_on = fail_press_on
        self._fail_release_on = fail_release_on
        # 讓 release 只失敗**前 N 次**。沒有這個旋鈕的話「一律失敗」會讓
        # `type_keyboard` 那支測試在**有沒有 finally 都一樣**的情況下通過——清理
        # 也失敗，於是兩種實作的事件記錄完全相同。第一版就是這樣寫的。
        self._release_failures = release_failures
        self._error = error or AutoControlKeyboardException("backend refused")
        # 放開失敗時丟的例外。預設與按下失敗同一個物件；要分辨「呼叫端看到的是
        # 哪一個」時給一個不同的。
        self._release_error = release_error or self._error

    def press(self, keycode, is_shift=False, skip_record=False):
        if keycode == self._fail_press_on:
            raise self._error
        self.events.append(("press", keycode))
        return str(keycode)

    def release(self, keycode, is_shift=False, skip_record=False):
        if keycode == self._fail_release_on:
            if self._release_failures is None:
                raise self._release_error
            if self._release_failures > 0:
                self._release_failures -= 1
                raise self._release_error
        self.events.append(("release", keycode))
        return str(keycode)

    @property
    def still_held(self) -> list:
        """Keys pressed and not subsequently released, in press order."""
        held: list = []
        for kind, key in self.events:
            if kind == "press":
                held.append(key)
            elif key in held:
                held.remove(key)
        return held


@pytest.fixture
def recorder(monkeypatch):
    def _install(**kwargs):
        rec = _Recorder(**kwargs)
        monkeypatch.setattr(kb, "press_keyboard_key", rec.press)
        monkeypatch.setattr(kb, "release_keyboard_key", rec.release)
        monkeypatch.setattr(kb, "record_action_to_list",
                            lambda *a, **k: None)
        return rec
    return _install


# -- the premise the design rests on ---------------------------------------

def test_the_except_tuple_cannot_catch_the_exception_these_raise():
    """``AutoControlKeyboardException`` is under none of the five caught types.

    This is not trivia: it is the reason the cleanup lives in ``finally``. If
    this ever becomes false, a wider ``except`` would be an equally valid fix
    and this file's reasoning would need rewriting.
    """
    for caught in (OSError, RuntimeError, AttributeError, TypeError,
                   ValueError):
        assert not issubclass(AutoControlKeyboardException, caught), caught
    assert issubclass(AutoControlKeyboardException, Exception)


# -- hotkey ------------------------------------------------------------------

def test_hotkey_releases_everything_on_the_happy_path(recorder):
    """Positive control. Without this, "always release" would also pass for an
    implementation that never presses anything at all."""
    rec = recorder()
    kb.hotkey(["ctrl", "shift", "esc"])
    assert rec.events == [
        ("press", "ctrl"), ("press", "shift"), ("press", "esc"),
        ("release", "esc"), ("release", "shift"), ("release", "ctrl"),
    ]
    assert rec.still_held == []


def test_hotkey_releases_the_keys_it_already_pressed_when_a_press_fails(
        recorder):
    """The expensive shape: ``ctrl`` and ``shift`` are down when ``esc`` fails."""
    rec = recorder(fail_press_on="esc")
    with pytest.raises(AutoControlKeyboardException):
        kb.hotkey(["ctrl", "shift", "esc"])
    assert rec.still_held == [], (
        f"left held down: {rec.still_held} — a stuck modifier changes the "
        "meaning of every later click")
    # Released in reverse press order, exactly as the happy path does.
    assert rec.events[-2:] == [("release", "shift"), ("release", "ctrl")]


def test_hotkey_releases_the_rest_when_a_release_fails(recorder):
    """A failing *release* must not abandon the keys still down behind it."""
    rec = recorder(fail_release_on="esc")
    with pytest.raises(AutoControlKeyboardException):
        kb.hotkey(["ctrl", "shift", "esc"])
    # `esc` genuinely could not be released — that is the backend's answer, and
    # the cleanup does not pretend otherwise. What must not happen is the other
    # two staying down because of it.
    assert "shift" not in rec.still_held and "ctrl" not in rec.still_held, (
        f"one failing release stranded the others: {rec.still_held}")


def test_hotkey_never_releases_a_key_it_did_not_press(recorder):
    """The first key fails, so nothing was ever pressed — release nothing.

    Getting this wrong is not harmless: releasing a key the user is physically
    holding would cancel their own keypress.
    """
    rec = recorder(fail_press_on="ctrl")
    with pytest.raises(AutoControlKeyboardException):
        kb.hotkey(["ctrl", "shift", "esc"])
    assert rec.events == [], f"released something it never pressed: {rec.events}"


def test_hotkey_handles_the_same_key_twice(recorder):
    """A duplicated key must not confuse the held-key bookkeeping.

    ``list.remove()`` would drop the *first* match; the implementation pops the
    stack instead, which is why this passes.
    """
    rec = recorder(fail_press_on="esc")
    with pytest.raises(AutoControlKeyboardException):
        kb.hotkey(["ctrl", "ctrl", "esc"])
    assert rec.still_held == [], rec.still_held
    assert rec.events.count(("release", "ctrl")) == 2


def test_a_failing_cleanup_does_not_replace_the_original_error(recorder):
    """If the cleanup release also fails, the caller must still see the
    original failure — not a second one raised from ``finally``."""
    original = AutoControlKeyboardException("press refused")
    from_cleanup = AutoControlKeyboardException("release refused")
    rec = recorder(fail_press_on="esc", fail_release_on="shift",
                   error=original, release_error=from_cleanup)
    with pytest.raises(AutoControlKeyboardException) as caught:
        kb.hotkey(["ctrl", "shift", "esc"])
    # Two distinct objects, so identity says which one escaped: a cleanup that
    # re-raised would surface `from_cleanup` here instead.
    assert caught.value is original, caught.value
    # And it kept going: `ctrl` was still released after `shift` failed.
    assert ("release", "ctrl") in rec.events


# -- type_keyboard -----------------------------------------------------------

def test_type_keyboard_releases_on_the_happy_path(recorder):
    rec = recorder()
    kb.type_keyboard("a")
    assert rec.events == [("press", "a"), ("release", "a")]
    assert rec.still_held == []


def test_type_keyboard_does_not_leave_the_key_down_when_release_fails(
        recorder):
    """press succeeded, release raised — without the ``finally`` the key stays
    down forever.

    The backend fails the release **once** and then works. That detail is what
    gives this test teeth: with a backend that always fails, the cleanup fails
    too and the recorded events are identical whether or not the ``finally``
    exists — the test would pass against the unfixed code.
    """
    rec = recorder(fail_release_on="a", release_failures=1)
    with pytest.raises(AutoControlKeyboardException):
        kb.type_keyboard("a")
    assert rec.still_held == [], (
        f"the key was left down: {rec.still_held}")
    assert rec.events == [("press", "a"), ("release", "a")], rec.events


def test_type_keyboard_releases_nothing_when_the_press_fails(recorder):
    rec = recorder(fail_press_on="a")
    with pytest.raises(AutoControlKeyboardException):
        kb.type_keyboard("a")
    assert rec.events == [], f"released a key it never pressed: {rec.events}"


def test_the_cleanup_helper_never_raises(recorder):
    """``_release_still_held`` runs from ``finally``; an exception there would
    replace the original error, which is the one the caller needs."""
    rec = recorder(fail_release_on="ctrl")
    held = ["ctrl"]
    kb._release_still_held(held, False)   # must not raise
    assert held == [], "the list must be drained even when a release fails"
    assert rec.events == []
