"""Phase 7.10: self-healing replay tests."""
from je_auto_control.utils.semantic_recording import (
    SelfHealingReplayer, self_healing_replay,
)


def _click(x: int, y: int, anchor: dict | None = None) -> dict:
    action = {"action": "mouse_click", "x": x, "y": y, "button": "left"}
    if anchor:
        action["anchor"] = anchor
    return action


# --- happy path ------------------------------------------------------

def test_replay_passes_when_every_step_succeeds():
    actions = [_click(10, 20), _click(30, 40)]
    seen = []
    rep = SelfHealingReplayer(
        execute_step=lambda a: seen.append((a["x"], a["y"])),
    )
    result = rep.replay(actions)
    assert result.succeeded is True
    assert result.healed_count == 0
    assert seen == [(10, 20), (30, 40)]
    assert [s.attempts for s in result.steps] == [1, 1]


# --- self-healing on failure -----------------------------------------

def test_failed_step_uses_vlm_to_relocate_and_retries():
    """First attempt at (10,20) verify-fails; VLM points to (99,77); retry passes."""
    attempts = []

    def execute(action):
        attempts.append((action["x"], action["y"]))

    def verify(action, _result):
        return action["x"] == 99  # only the VLM-supplied coords pass

    def vlm(description):
        assert "Login" in description
        return (99, 77)

    actions = [_click(10, 20, anchor={"role": "Button", "name": "Login"})]
    result = SelfHealingReplayer(
        execute_step=execute, verify_step=verify, vlm_locate=vlm,
    ).replay(actions)
    assert result.succeeded is True
    assert result.healed_count == 1
    assert attempts == [(10, 20), (99, 77)]
    assert result.steps[0].healed is True
    assert result.steps[0].attempts == 2


def test_exhausted_retries_returns_failure():
    """Both the original coords and the VLM-supplied ones fail."""

    def verify(_action, _result):
        return False  # always fails

    def vlm(_desc):
        return (5, 5)

    actions = [_click(10, 20, anchor={"role": "Button", "name": "X"})]
    result = SelfHealingReplayer(
        execute_step=lambda _a: None,
        verify_step=verify, vlm_locate=vlm, max_retries=2,
    ).replay(actions)
    assert result.succeeded is False
    assert result.steps[0].success is False
    assert result.steps[0].attempts == 3  # original + 2 retries


def test_no_anchor_means_no_self_healing():
    """A step without an anchor falls back to plain retry (no VLM call)."""
    vlm_called = []

    def vlm(desc):
        vlm_called.append(desc)
        return (1, 1)

    actions = [_click(10, 20)]  # no anchor field
    result = SelfHealingReplayer(
        execute_step=lambda _a: None,
        verify_step=lambda _a, _r: False,
        vlm_locate=vlm, max_retries=2,
    ).replay(actions)
    assert result.succeeded is False
    assert vlm_called == []  # VLM never invoked


def test_no_vlm_means_no_self_healing():
    """Without a VLM callable, the replayer just returns the failure."""
    actions = [_click(10, 20, anchor={"role": "Button", "name": "X"})]
    result = SelfHealingReplayer(
        execute_step=lambda _a: None,
        verify_step=lambda _a, _r: False,
        vlm_locate=None,
        max_retries=2,
    ).replay(actions)
    assert result.succeeded is False
    assert result.steps[0].healed is False


def test_execute_step_exception_is_treated_as_failure():
    attempts = []

    def execute(action):
        attempts.append(action["x"])
        if action["x"] == 10:
            raise RuntimeError("can't click there")

    def vlm(_desc):
        return (50, 50)

    actions = [_click(10, 20, anchor={"role": "Button", "name": "Save"})]
    result = SelfHealingReplayer(
        execute_step=execute, vlm_locate=vlm,
    ).replay(actions)
    assert result.succeeded is True
    assert attempts == [10, 50]


def test_subsequent_steps_skipped_after_failure():
    """Once a step fails, the rest of the recording is not executed."""

    seen = []

    def execute(action):
        seen.append(action["x"])
        raise RuntimeError("boom")

    actions = [_click(10, 0), _click(20, 0)]
    result = SelfHealingReplayer(
        execute_step=execute, max_retries=0,
    ).replay(actions)
    assert result.succeeded is False
    assert seen == [10]  # second step never ran
    assert len(result.steps) == 1


def test_convenience_wrapper_round_trip():
    seen = []
    result = self_healing_replay(
        [_click(1, 2), _click(3, 4)],
        execute_step=lambda a: seen.append(a["x"]),
    )
    assert result.succeeded is True
    assert seen == [1, 3]


def test_anchor_description_includes_app_name():
    """The VLM hint should mention the app when the anchor knows one."""
    captured = []

    def vlm(desc):
        captured.append(desc)
        return (9, 9)

    actions = [_click(
        0, 0,
        anchor={"role": "Button", "name": "Submit", "app_name": "ShopApp"},
    )]
    SelfHealingReplayer(
        execute_step=lambda _a: None,
        verify_step=lambda _a, _r: _a["x"] == 9,
        vlm_locate=vlm,
    ).replay(actions)
    assert captured and "ShopApp" in captured[0]
    assert "Submit" in captured[0]
