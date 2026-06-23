"""Headless tests for the settle decision over a churn series (pure stdlib)."""
import je_auto_control as ac
from je_auto_control.utils.settle_detector import (
    SettleTracker, is_settled, settle_point,
)


def test_settle_point_after_quiet_run():
    # 5, 4 are noisy; then three values <= 1.0 → settled at index 4
    assert settle_point([5, 4, 0.5, 0.3, 0.2], quiet_samples=3,
                        max_churn=1.0) == 4


def test_spike_resets_quiet_run():
    # quiet, quiet, SPIKE, quiet x3 → settles only at the final index
    assert settle_point([0.2, 0.2, 5, 0.1, 0.1, 0.1], quiet_samples=3,
                        max_churn=1.0) == 5


def test_never_settles_is_none():
    assert settle_point([5, 4, 3], quiet_samples=2, max_churn=1.0) is None


def test_is_settled_bool():
    assert is_settled([0.1, 0.1], quiet_samples=2, max_churn=1.0) is True
    assert is_settled([9, 8], quiet_samples=2, max_churn=1.0) is False


def test_tracker_incremental_and_reset():
    tracker = SettleTracker(quiet_samples=2, max_churn=1.0)
    assert tracker.update(0.5).settled is False
    state = tracker.update(0.4)
    assert state.settled is True and state.quiet_run == 2
    tracker.reset()
    assert tracker.update(0.3).settled is False   # run cleared


# --- wiring ---------------------------------------------------------------

def test_wiring():
    assert "AC_settle_point" in set(ac.executor.known_commands())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_settle_point" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_settle_point" in specs


def test_facade_exports():
    for name in ("settle_point", "is_settled", "SettleTracker", "SettleState"):
        assert hasattr(ac, name) and name in ac.__all__
