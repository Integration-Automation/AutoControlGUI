"""Round-3 regression: AgentLoop._dispatch_tool must record AutoControl*
exceptions and TypeErrors per-step (loop continues) instead of crashing the
whole run."""
from je_auto_control.utils.agent import AgentLoop, FakeAgentBackend
from je_auto_control.utils.exception.exceptions import AutoControlMouseException


def _run_with_failing_runner(exc):
    def runner(_name, _args):
        raise exc

    backend = FakeAgentBackend([
        {"tool": "AC_click_mouse", "input": {"button": "left"}},
        {"stop": True, "message": "done"},
    ])
    return AgentLoop(
        backend, tool_runner=runner, screenshot_fn=lambda: None,
    ).run("goal")


def test_autocontrol_exception_recorded_and_loop_continues():
    result = _run_with_failing_runner(AutoControlMouseException("boom"))
    failing = next(s for s in result.steps if s.tool == "AC_click_mouse")
    assert failing.error is not None
    assert "AutoControlMouseException" in failing.error
    # The loop kept going to the stop decision rather than aborting the run.
    assert result.succeeded is True
    assert result.final_message == "done"


def test_type_error_from_hallucinated_kwarg_recorded_and_loop_continues():
    result = _run_with_failing_runner(
        TypeError("unexpected keyword argument 'foo'"),
    )
    failing = next(s for s in result.steps if s.tool == "AC_click_mouse")
    assert failing.error is not None
    assert "TypeError" in failing.error
    assert result.succeeded is True
