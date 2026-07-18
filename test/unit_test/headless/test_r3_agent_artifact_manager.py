"""Round-3 regression: capture_error_snapshot must swallow the
AutoControlScreenException that ``screenshot`` raises on a locked/headless
session, so the snapshot step never masks the original failure."""
import sys
import types

from je_auto_control.utils.exception.exceptions import AutoControlScreenException
from je_auto_control.utils.run_history.artifact_manager import (
    capture_error_snapshot,
)


class _FakeStore:
    def __init__(self):
        self.attached = []

    def attach_artifact(self, run_id, path):
        self.attached.append((run_id, path))


def _install_failing_screenshot(monkeypatch, exc):
    module = types.ModuleType("je_auto_control.wrapper.auto_control_screen")

    def screenshot(_path):
        raise exc

    module.screenshot = screenshot
    monkeypatch.setitem(
        sys.modules, "je_auto_control.wrapper.auto_control_screen", module,
    )


def test_screen_exception_is_swallowed(monkeypatch, tmp_path):
    _install_failing_screenshot(
        monkeypatch, AutoControlScreenException("no display"),
    )
    store = _FakeStore()
    result = capture_error_snapshot(7, artifacts_dir=tmp_path, store=store)
    assert result is None
    assert store.attached == []
