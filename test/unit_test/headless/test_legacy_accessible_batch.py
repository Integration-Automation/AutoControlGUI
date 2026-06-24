"""Headless tests for the MSAA bridge (LegacyIAccessiblePattern, fake backend)."""
import je_auto_control as ac
from je_auto_control.utils.accessibility.backends import base as backend_base
from je_auto_control.utils.legacy_accessible import (
    legacy_default_action, legacy_info,
)

_INFO = {"name": "OK", "value": "", "description": "Accept the dialog",
         "default_action": "Press", "role": 43, "state": 1048576}


class _FakeBackend(backend_base.AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self, info=None):
        self.info = info
        self.actions = []

    def legacy_info(self, name=None, role=None, app_name=None, automation_id=None):
        return self.info

    def legacy_default_action(self, name=None, role=None, app_name=None,
                              automation_id=None):
        self.actions.append(name)
        return True


def _inject(monkeypatch, backend):
    import je_auto_control.utils.accessibility.backends as backends
    monkeypatch.setattr(backends, "_cached_backend", backend, raising=False)


def test_legacy_info_dispatch(monkeypatch):
    _inject(monkeypatch, _FakeBackend(dict(_INFO)))
    assert legacy_info(name="OK", role="button") == _INFO


def test_legacy_info_not_found(monkeypatch):
    _inject(monkeypatch, _FakeBackend(None))
    assert legacy_info(name="missing") is None


def test_legacy_default_action(monkeypatch):
    fake = _FakeBackend()
    _inject(monkeypatch, fake)
    assert legacy_default_action(name="OK") is True
    assert fake.actions == ["OK"]


def test_unsupported_backend_raises(monkeypatch):
    from je_auto_control.utils.accessibility.element import (
        AccessibilityNotAvailableError)
    _inject(monkeypatch, backend_base.AccessibilityBackend())
    try:
        legacy_info(name="x")
        raised = False
    except AccessibilityNotAvailableError:
        raised = True
    assert raised is True


# --- wiring ---------------------------------------------------------------

def test_executor_adapters(monkeypatch):
    _inject(monkeypatch, _FakeBackend(dict(_INFO)))
    from je_auto_control.utils.executor.action_executor import (
        _legacy_default_action, _legacy_info)
    out = _legacy_info(name="OK")
    assert out["found"] is True and out["info"]["default_action"] == "Press"
    assert _legacy_default_action(name="OK") is True


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_legacy_info", "AC_legacy_default_action"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_legacy_info", "ac_legacy_default_action"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_legacy_info", "AC_legacy_default_action"} <= specs


def test_facade_exports():
    for name in ("legacy_info", "legacy_default_action"):
        assert hasattr(ac, name) and name in ac.__all__
