"""Round-3 net audit: trigger poll loops must contain framework exceptions.

Every framework error now subclasses ``AutoControlException``. These triggers
reach out to the screen / a script file — all of which raise members of that
family in the *normal* course of polling (image not on screen yet, script
renamed). Before the fix their catch tuples missed the base, so the offender
was permanently disabled (image/pixel/window triggers), a bad email re-fired
forever, or an HTTP webhook client got a dropped connection.
"""
import time

import pytest

import je_auto_control.wrapper.auto_control_image as image_mod
import je_auto_control.wrapper.auto_control_screen as screen_mod
import je_auto_control.wrapper.auto_control_window as window_mod
from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, AutoControlJsonActionException,
    AutoControlScreenException, ImageNotFoundException,
)
from je_auto_control.utils.triggers import email_trigger as et
from je_auto_control.utils.triggers import webhook_server as ws
from je_auto_control.utils.triggers.trigger_engine import (
    ImageAppearsTrigger, PixelColorTrigger, TriggerEngine, WindowAppearsTrigger,
)


class _FakeHistory:
    """Records finish_run status so a test can assert OK vs ERROR."""

    def __init__(self) -> None:
        self.finished: list = []

    def start_run(self, *args, **kwargs) -> int:
        return 1

    def finish_run(self, run_id, status, error_text, artifact_path=None) -> bool:
        self.finished.append((run_id, status, error_text))
        return True


# --- finding 1: image / pixel / window triggers ----------------------------

def test_image_trigger_returns_false_when_image_absent(monkeypatch):
    """ImageNotFoundException on an absent template is the normal poll case."""
    def raise_not_found(*_args, **_kwargs):
        raise ImageNotFoundException("absent")

    monkeypatch.setattr(image_mod, "locate_image_center", raise_not_found)
    trigger = ImageAppearsTrigger(
        trigger_id="img", script_path="s.json", image_path="x.png")
    assert trigger.is_fired() is False  # must not raise


def test_pixel_trigger_returns_false_on_screen_exception(monkeypatch):
    def raise_screen(*_args, **_kwargs):
        raise AutoControlScreenException("no display")

    monkeypatch.setattr(screen_mod, "get_pixel", raise_screen)
    trigger = PixelColorTrigger(
        trigger_id="px", script_path="s.json", x=1, y=1)
    assert trigger.is_fired() is False


def test_window_trigger_returns_false_on_framework_exception(monkeypatch):
    def raise_action(*_args, **_kwargs):
        raise AutoControlActionException("backend blew up")

    monkeypatch.setattr(window_mod, "find_window", raise_action)
    trigger = WindowAppearsTrigger(
        trigger_id="win", script_path="s.json", title_substring="Save")
    assert trigger.is_fired() is False


def test_engine_keeps_image_trigger_enabled_when_image_absent(monkeypatch):
    """End-to-end: a normally-absent image must not disable the trigger."""
    def raise_not_found(*_args, **_kwargs):
        raise ImageNotFoundException("absent")

    monkeypatch.setattr(image_mod, "locate_image_center", raise_not_found)
    engine = TriggerEngine(executor=lambda actions: None, tick_seconds=0.05)
    engine.add(ImageAppearsTrigger(
        trigger_id="img", script_path="s.json", image_path="x.png",
        repeat=True))
    engine.start()
    time.sleep(0.3)
    try:
        assert engine._thread.is_alive()
        assert engine._triggers["img"].enabled is True
    finally:
        engine.stop()


# --- finding 2: email trigger ---------------------------------------------

def test_decode_header_unknown_charset_does_not_raise():
    """An unknown charset raises LookupError from the codec lookup."""
    from email.header import decode_header, make_header
    poisoned = "=?x-unknown-charset?B?SGVsbG8=?="
    # Prove the input genuinely triggers the LookupError path the old
    # `except ValueError` could not catch.
    with pytest.raises(LookupError):
        str(make_header(decode_header(poisoned)))
    # The helper must swallow it and fall back to the raw value.
    assert et._decode_header_value(poisoned) == poisoned


def test_email_fire_marks_uid_seen_and_records_error_on_missing_script(
        monkeypatch):
    """A missing script must record STATUS_ERROR and stop the uid re-firing."""
    fake_hist = _FakeHistory()
    monkeypatch.setattr(et, "default_history_store", fake_hist)
    monkeypatch.setattr(et, "capture_error_snapshot", lambda run_id: None)

    def missing_script(_path):
        raise AutoControlJsonActionException("script gone")

    monkeypatch.setattr(et, "read_action_json", missing_script)
    monkeypatch.setattr(et, "_fetch_message", lambda client, uid: object())
    monkeypatch.setattr(et, "_build_payload",
                        lambda uid, msg: {"email.uid": uid})
    monkeypatch.setattr(et, "_mark_seen", lambda client, uid: None)

    watcher = et.EmailTriggerWatcher(
        executor=lambda actions, variables: None)
    trigger = et.EmailTrigger(
        trigger_id="t1", host="h", username="u", password="p",
        script_path="missing.json")

    fired = watcher._fire_for_uid(client=object(), trigger=trigger, uid=b"42")

    assert fired == 1
    assert "42" in trigger._seen_uids  # processed -> no infinite re-fire
    assert fake_hist.finished, "a run must have been finished"
    assert fake_hist.finished[-1][1] == "error"  # not a bogus STATUS_OK
    assert trigger.last_error is not None


# --- finding 3: webhook server --------------------------------------------

def test_webhook_fire_records_failure_and_returns_when_script_raises(
        monkeypatch):
    """A framework error must set last_status=500 and let fire() return."""
    fake_hist = _FakeHistory()
    monkeypatch.setattr(ws, "default_history_store", fake_hist)
    monkeypatch.setattr(ws, "capture_error_snapshot", lambda run_id: None)
    monkeypatch.setattr(ws, "read_action_json", lambda path: [{"AC_x": {}}])

    def boom(actions, variables):
        raise AutoControlActionException("unknown command")

    server = ws.WebhookTriggerServer(executor=boom)
    trigger = server.add("/hook", "script.json")

    run_id = server.fire(trigger, {"webhook.method": "POST"})  # must not raise

    assert run_id is not None
    assert trigger.last_status == 500
    assert fake_hist.finished[-1][1] == "error"
