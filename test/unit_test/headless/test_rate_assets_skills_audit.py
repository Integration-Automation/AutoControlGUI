"""Named rate limits, app-idle polling, retry jitter, asset types, memory reads, skills, locators, sagas.

``AC_rate_limit`` ignored a changed rate for a reused name; the idle wait slept
an hour on a one-second timeout and spun at 0; an unknown jitter became full
jitter and an infinite cap reached JSON; assets stored 3.7 as 3 and
"enabled" as False; a memory store raised when read during a write; tags
typed as one string were split into letters; a self-calling skill recursed;
a blank locator matched the desktop; the MCP saga dropped its rollback errors.
"""
import json
import threading

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException


def test_a_reused_limiter_name_takes_the_new_rate_on_both_surfaces():
    from je_auto_control.utils.executor.action_executor import _rate_limit
    from je_auto_control.utils.mcp_server.tools._handlers_operations import rate_limit
    # A slow rate: the bucket refills between calls (3.0001 on a busy machine).
    _rate_limit("audit-bucket", rate=0.001, capacity=1)
    assert _rate_limit("audit-bucket", rate=0.001, capacity=5)["acquired"]
    assert rate_limit("audit-bucket", rate=0.001, capacity=5)["tokens"] == pytest.approx(3.0, abs=0.01)


@pytest.mark.parametrize("interval, bound", [(3600.0, 1.0), (0.0, 0.05), (float("nan"), 0.05), (-1.0, 0.05)])
def test_the_idle_wait_keeps_its_deadline_and_never_spins(interval, bound):
    from je_auto_control.utils.app_idle.app_idle import wait_until_app_idle
    now, slept = [0.0], []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds
        if len(slept) > 100:
            raise AssertionError("the wait spun")

    result = wait_until_app_idle(busy_probe=lambda: True, timeout_s=1.0, interval_s=interval,
                                 clock=lambda: now[0], sleep=sleep)
    assert result["idle"] is False and max(slept) <= 1.0
    assert len(slept) <= round(1.0 / bound) + 1


@pytest.mark.parametrize("jitter", ["None", "nnone", "fast"])
def test_an_unknown_jitter_is_refused(jitter):
    from je_auto_control.utils.retry_budget import RetryBudget
    if jitter == "None":
        assert RetryBudget(jitter=jitter).jitter == "none"
        return
    with pytest.raises(ValueError):
        RetryBudget(jitter=jitter)


def test_retry_delays_stay_finite_and_bounded():
    from je_auto_control.utils.executor.action_executor import _plan_retry_delays, _retry_delay
    from je_auto_control.utils.retry_budget import backoff_delay
    with pytest.raises(ValueError):
        _retry_delay(2000, max_delay=float("inf"))
    with pytest.raises(ValueError):
        _plan_retry_delays(3_000_000)
    assert backoff_delay(5000, base=0.0, max_delay=5.0, multiplier=2.0) == 0.0
    assert _retry_delay(1, jitter=None)["delay"] == 0.1


@pytest.mark.parametrize("value, asset_type", [(3.7, "int"), (True, "int"), (float("inf"), "int"),
                                               ("enabled", "bool")])
def test_an_asset_type_refuses_values_it_cannot_hold(value, asset_type):
    from je_auto_control.utils.assets import AssetStore
    with pytest.raises(ValueError):
        AssetStore(None).set("x", value, asset_type=asset_type)


def test_asset_types_keep_what_they_can_hold():
    from je_auto_control.utils.assets import AssetStore
    store = AssetStore(None)
    store.set("port", 8080.0, asset_type="int")
    store.set("flag", "off", asset_type="bool")
    assert store.get("port").value == 8080 and store.get("flag").value is False


def test_a_memory_store_can_be_read_while_it_is_written():
    import time

    from je_auto_control.utils.json_store import SharedJsonDict
    store = SharedJsonDict(None)
    store.update(lambda data: data.update({f"k{i}": i for i in range(50)}))
    errors, done = [], threading.Event()

    def toggle(data):
        # Changes the dict's size every call without letting it grow.
        if data.pop("extra", None) is None:
            data["extra"] = 1

    def writer():
        while not done.is_set():
            store.update(toggle)
            time.sleep(0)

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        for _ in range(50):
            try:
                for _item in store.read().items():
                    time.sleep(0)            # let the writer run mid-iteration
            except RuntimeError as error:
                errors.append(error)
    finally:
        done.set()
        thread.join(2)
    assert not errors
    snapshot = store.read()
    snapshot["mine"] = 1
    assert "mine" not in store.read()


def test_hand_written_skills_keep_their_tags_and_bad_entries_are_skipped(tmp_path):
    from je_auto_control.utils.skill_library import SkillLibrary
    path = tmp_path / "skills.json"
    path.write_text(json.dumps({"sign_in": {"actions": [["AC_retry_delay", {"attempt": 1}]], "tags": "login"},
                                "numbers": {"actions": [["AC_retry_delay", {"attempt": 1}]], "tags": [1, 2]},
                                "broken": "not an object"}), encoding="utf-8")
    library = SkillLibrary(str(path))
    assert library.get("sign_in").tags == ["login"]
    assert [skill.name for skill in library.search("login")] == ["sign_in"]
    assert library.search("l o") == []
    assert library.names() == ["numbers", "sign_in"]


def test_a_self_calling_skill_fails_at_the_top_and_the_script_goes_on(tmp_path):
    from je_auto_control.utils.executor.action_executor import Executor
    from je_auto_control.utils.skill_library import SkillLibrary
    path = str(tmp_path / "skills.json")
    SkillLibrary(path).save("loop", [["AC_skill_run", {"path": path, "name": "loop"}]])
    record = Executor().execute_action([["AC_skill_run", {"path": path, "name": "loop"}],
                                        ["AC_retry_delay", {"attempt": 1}]])
    first, second = record.values()
    assert "nested deeper than" in str(first) and len(str(first)) < 300
    assert second == {"delay": 0.1}


def test_blank_locators_are_refused_and_bad_entries_skipped(tmp_path):
    from je_auto_control.utils.element_repository import ElementRepository
    path = tmp_path / "repo.json"
    path.write_text(json.dumps({"ok": {"name": "OK"}, "cancel": "Cancel"}), encoding="utf-8")
    repository = ElementRepository(str(path))
    assert repository.keys() == ["ok"]
    with pytest.raises(ValueError):
        repository.save("login.submit", name="  ")


def test_the_mcp_saga_reports_rollback_errors_and_bad_steps_are_refused():
    from je_auto_control.utils.mcp_server.tools._handlers_operations import run_saga
    steps = [{"name": "s1", "action": [["AC_retry_delay", {"attempt": 1}]],
              "compensation": [["AC_does_not_exist"]]},
             {"name": "s2", "action": [["AC_also_missing"]]}]
    result = run_saga(steps)
    assert result["failed_step"] == "s2" and "s1" in result["compensation_errors"]
    with pytest.raises(ValueError):
        run_saga([["AC_retry_delay", {"attempt": 1}]])
    dict_form = run_saga([{"name": "s", "action": {"auto_control": [["AC_retry_delay", {"attempt": 1}]]}}])
    assert dict_form["ok"]


def test_rate_limit_library_edges_are_refused():
    from je_auto_control.utils.rate_limit import SlidingWindowLimiter, TokenBucket, throttle
    with pytest.raises(AutoControlException):
        TokenBucket(1, 1).acquire(2 * 0.5, timeout=float("nan"))
    for limit in (0.5, float("inf")):
        with pytest.raises(AutoControlException):
            SlidingWindowLimiter(limit, 1.0)
    with pytest.raises(AutoControlException):
        throttle(float("nan"))
