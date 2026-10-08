"""``ac.execute_action`` forwards the executor's keywords.

The module-level function took the list only, so ``dry_run``, ``raise_on_error``
and ``step_callback`` were reachable only as ``ac.executor.execute_action``.
One inert fake command; nothing is driven.
"""
import inspect

import pytest

import je_auto_control as ac
from je_auto_control.utils.exception.exceptions import AutoControlException


@pytest.fixture()
def fake_command():
    """One inert command on the shared executor, removed afterwards."""
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        if kwargs.get("fail"):
            raise AutoControlException("asked to fail")
        return len(calls)

    ac.executor.event_dict["AC_facade_fake"] = fake
    yield calls
    ac.executor.event_dict.pop("AC_facade_fake", None)


def test_a_positional_call_behaves_as_before(fake_command):
    record = ac.execute_action([["AC_facade_fake", {"n": 1}]])
    assert list(record.values()) == [1] and fake_command == [{"n": 1}]


def test_dry_run_is_forwarded(fake_command):
    record = ac.execute_action([["AC_facade_fake", {"n": 1}]], dry_run=True)
    assert fake_command == [] and list(record.values()) == ["(not executed)"]


def test_raise_on_error_is_forwarded(fake_command):
    recorded = ac.execute_action([["AC_facade_fake", {"fail": True}]])
    assert "asked to fail" in next(iter(recorded.values()))
    with pytest.raises(AutoControlException, match="asked to fail"):
        ac.execute_action([["AC_facade_fake", {"fail": True}]], raise_on_error=True)


def test_step_callback_is_forwarded(fake_command):
    seen = []
    ac.execute_action([["AC_facade_fake", {"n": 1}], ["AC_facade_fake", {"n": 2}]],
                      step_callback=seen.append)
    assert [action[1]["n"] for action in seen] == [1, 2]


def test_the_keywords_are_keyword_only_and_match_the_executor():
    module_level = inspect.signature(ac.execute_action).parameters
    method = inspect.signature(ac.executor.execute_action).parameters
    for name in ("raise_on_error", "dry_run", "step_callback"):
        assert module_level[name].kind is inspect.Parameter.KEYWORD_ONLY
        assert module_level[name].default == method[name].default
    assert "_validated" not in module_level
    with pytest.raises(TypeError):
        inspect.signature(ac.execute_action).bind([["AC_facade_fake"]], True)
