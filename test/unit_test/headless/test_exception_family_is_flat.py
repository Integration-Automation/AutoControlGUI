"""Every framework error must subclass ``AutoControlException``.

The hierarchy is flat on purpose: the containment boundaries — the executor's
per-action `except`, the background poll loops, the REST/socket/MCP request
handlers, the GUI slots — all catch the family in one clause. A class that
inherits ``Exception`` directly is caught by none of them, so one malformed
argument to one command aborts the whole script instead of being recorded as a
failed action. That is not hypothetical: ``ConfigBundleError`` did exactly that
through ``AC_config_import``, and ``UsbClientError`` could through
``AC_usb_remote_devices``.

The rule is checked structurally rather than class by class, because the way it
gets broken is a *new* subsystem defining its own error — which no list of
existing classes would notice.
"""
import ast
import pathlib

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException

#: The package tree, read as source: importing every module to inspect its
#: classes would drag in optional backends this test does not need.
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parents[3] / "je_auto_control"

#: Deliberately outside the family, and each for a reason that would break if
#: it were inside:
#:
#: * ``LoopBreak`` / ``LoopContinue`` are control flow, not failure. The
#:   executor re-raises them *before* the family clause; making them relatives
#:   would let a plain ``except AutoControlException`` swallow a ``break``.
#: * ``_MCPError`` carries a JSON-RPC error code to the dispatcher that raised
#:   it, and is caught there by name. It never crosses a boundary.
#: * ``AutoControlException`` is the root of the family, so it is the one class
#:   that has to inherit ``Exception`` itself.
DELIBERATELY_OUTSIDE = {
    ("utils/exception/exceptions.py", "AutoControlException"),
    ("utils/executor/flow_control.py", "LoopBreak"),
    ("utils/executor/flow_control.py", "LoopContinue"),
    ("utils/mcp_server/_protocol.py", "_MCPError"),
}


def _classes_inheriting_exception_directly():
    """Yield ``(relative path, class name)`` for every ``class X(Exception)``."""
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id == "Exception":
                    rel = path.relative_to(PACKAGE_ROOT).as_posix()
                    yield rel, node.name


def test_no_framework_error_escapes_the_family():
    """Only the three control-flow carriers may inherit ``Exception``."""
    found = set(_classes_inheriting_exception_directly())
    unexpected = found - DELIBERATELY_OUTSIDE
    assert not unexpected, (
        "these inherit Exception directly, so every containment boundary "
        "misses them — derive them from AutoControlException, or add them to "
        f"DELIBERATELY_OUTSIDE with the reason: {sorted(unexpected)}")

    # And the allowlist itself has to stay real: a stale entry would quietly
    # licence a class that no longer exists, or has since been reparented.
    stale = DELIBERATELY_OUTSIDE - found
    assert not stale, f"allowlisted classes that are no longer there: {stale}"


@pytest.mark.parametrize("module_path, class_name", [
    ("je_auto_control.utils.config_bundle.config_bundle", "ConfigBundleError"),
    ("je_auto_control.utils.usb.passthrough.protocol", "ProtocolError"),
    ("je_auto_control.utils.usb.passthrough.session", "SessionError"),
    ("je_auto_control.utils.usb.passthrough.viewer_client", "UsbClientError"),
    ("je_auto_control.utils.work_queue.work_queue", "BusinessError"),
])
def test_the_reparented_five_are_in_the_family(module_path, class_name):
    """The classes that used to escape, named so the fix is legible."""
    module = pytest.importorskip(module_path)
    assert issubclass(getattr(module, class_name), AutoControlException)


def test_a_rejected_config_bundle_does_not_abort_the_script():
    """The failure that proved the rule matters, pinned end to end.

    ``AC_config_import`` on a malformed bundle used to raise past the
    per-action boundary and take every remaining action with it, even under
    ``raise_on_error=False``.
    """
    from je_auto_control.utils.executor.action_executor import executor

    record = executor.execute_action(
        [["AC_config_import", {"bundle": {"not": "a bundle"}}],
         ["AC_sleep", {"sleep_time": 0.01}]],
        raise_on_error=False)

    assert len(record) == 2, "the second action never ran"
    assert any("ConfigBundleError" in str(value) for value in record.values())
