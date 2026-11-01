"""A list may load a package and use it, when the gate allows that package.

``execute_action`` validates every command name before it runs anything, and
``AC_add_package_to_executor`` only registers ``<package>_<member>`` when it
runs -- so a list that loaded an allowed package and then used it was refused
for an unknown command whatever the gate said. Validation now leaves exactly
those names to run time: a name with the prefix of a package that a load
command names literally, earlier in the walk, and that the gate would allow.
Everything else is rejected up front as before.

``json`` is the package loaded here; only its members and a probe run.
"""
import json
from pathlib import Path

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlActionException
from je_auto_control.utils.executor.action_executor import Executor, executor
from je_auto_control.utils.executor.action_schema import (
    unknown_command_names, validate_actions,
)
from je_auto_control.utils.package_manager import package_manager_class
from je_auto_control.utils.package_manager.package_manager_class import PackageManager

PROBE = "AC_gate_probe"
_LOAD = ["AC_add_package_to_executor", ["json"]]
_USE = ["json_dumps", [[1, 2]]]
_REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _no_inherited_allowlist(monkeypatch):
    monkeypatch.delenv("JE_AUTOCONTROL_ALLOWED_PACKAGES", raising=False)


@pytest.fixture
def gate():
    """The shared gate, closed and empty; it and the command table are restored."""
    manager = package_manager_class.package_manager
    saved_gate = (manager.allow_arbitrary_packages, set(manager.allowed_packages))
    saved_commands = dict(executor.event_dict)
    manager.allow_arbitrary_packages, manager.allowed_packages = False, set()
    for name in [name for name in executor.event_dict if name.startswith("json_")]:
        del executor.event_dict[name]
    yield manager
    manager.allow_arbitrary_packages, manager.allowed_packages = saved_gate[0], saved_gate[1]
    executor.event_dict.clear()
    executor.event_dict.update(saved_commands)


@pytest.fixture
def ran(gate):
    """A probe command; the list records every call it receives."""
    calls = []
    executor.event_dict[PROBE] = lambda value=None: calls.append(value) or value
    return calls


def _values(record):
    return list(record.values())


# --- the defect -------------------------------------------------------------

def test_a_list_loads_an_allowed_package_and_uses_it(gate):
    gate.allow_packages("json")
    record = executor.execute_action([_LOAD, _USE])
    assert _values(record)[1] == "[1, 2]"


def test_the_keyword_form_of_the_load_command_counts_too(gate):
    gate.allow_packages("json")
    record = executor.execute_action(
        [["AC_add_package_to_executor", {"package": "json"}], _USE])
    assert _values(record)[1] == "[1, 2]"


def test_an_open_gate_defers_any_package_the_list_loads(gate):
    gate.set_allow_arbitrary_packages(True)
    record = executor.execute_action([_LOAD, _USE])
    assert _values(record)[1] == "[1, 2]"


def test_a_submodule_of_an_allowed_package_is_deferred(gate):
    gate.allow_packages("json")
    record = executor.execute_action([
        ["AC_add_package_to_executor", ["json.decoder"]],
        ["json.decoder_JSONDecoder"],
    ])
    assert "JSONDecoder object" in str(_values(record)[1])


def test_the_name_may_be_used_inside_a_nested_body(gate, ran):
    gate.allow_packages("json")
    record = executor.execute_action([
        _LOAD,
        ["AC_loop", {"times": 2, "body": [_USE, [PROBE, {"value": "x"}]]}],
    ])
    assert ran == ["x", "x"]
    assert "Unknown" not in str(record)


def test_a_load_inside_a_body_covers_what_follows_it(gate):
    gate.allow_packages("json")
    record = executor.execute_action([
        ["AC_loop", {"times": 1, "body": [_LOAD]}],
        _USE,
    ])
    assert _values(record)[1] == "[1, 2]"


# --- what is still rejected before anything runs ----------------------------

def _refused(actions, ran, name):
    with pytest.raises(AutoControlActionException, match=f"unknown command '{name}'"):
        executor.execute_action([[PROBE, {"value": "first"}], *actions])
    assert ran == []                                # nothing ran, not even the first action
    assert "json_dumps" not in executor.event_dict  # ...and nothing was imported


def test_a_package_the_gate_refuses_is_not_deferred(ran):
    _refused([_LOAD, _USE], ran, "json_dumps")


def test_a_name_used_before_its_load_is_rejected(gate, ran):
    gate.allow_packages("json")
    _refused([_USE, _LOAD], ran, "json_dumps")


def test_a_name_of_another_package_is_rejected(gate, ran):
    gate.allow_packages("json")
    _refused([_LOAD, ["os_getcwd"]], ran, "os_getcwd")


def test_the_bare_prefix_is_rejected(gate, ran):
    gate.allow_packages("json")
    _refused([_LOAD, ["json_"]], ran, "json_")


def test_an_unknown_name_elsewhere_in_the_list_is_still_rejected(gate, ran):
    gate.allow_packages("json")
    _refused([_LOAD, _USE, ["AC_no_such_command"]], ran, "AC_no_such_command")


@pytest.mark.parametrize("params", [
    ["${package}"], ["json", "extra"], [], {"name": "json"}, {"package": 7}, [["json"]],
], ids=["placeholder", "two-args", "no-args", "wrong-key", "not-a-string", "nested"])
def test_a_load_that_does_not_name_a_package_literally_defers_nothing(gate, ran, params):
    gate.set_allow_arbitrary_packages(True)
    _refused([["AC_add_package_to_executor", params], _USE], ran, "json_dumps")


def test_a_private_executor_never_receives_the_names_so_they_are_rejected(gate):
    gate.allow_packages("json")
    private = Executor()
    with pytest.raises(AutoControlActionException, match="unknown command 'json_dumps'"):
        private.execute_action([_LOAD, _USE])


def test_the_callback_executor_load_command_defers_nothing(gate, ran):
    gate.allow_packages("json")
    _refused([["AC_add_package_to_callback_executor", ["json"]], _USE], ran, "json_dumps")


# --- a deferred name is checked when its action runs ------------------------

def test_a_deferred_name_that_does_not_exist_fails_its_own_action(gate, ran):
    from je_auto_control.utils.executor.action_executor import (
        recorded_failures, reset_recorded_failures,
    )
    gate.allow_packages("json")
    reset_recorded_failures()
    record = executor.execute_action([
        _LOAD, ["json_no_such_member"], [PROBE, {"value": "after"}]])
    assert "Unknown action: json_no_such_member" in str(_values(record)[1])
    assert recorded_failures() == 1
    assert ran == ["after"]


def test_a_deferred_name_fails_loudly_under_raise_on_error(gate):
    gate.allow_packages("json")
    with pytest.raises(AutoControlActionException, match="Unknown action: json_no_such_member"):
        executor.execute_action([_LOAD, ["json_no_such_member"]], raise_on_error=True)


# --- the other validators agree ---------------------------------------------

def test_unknown_commands_in_follows_the_same_rule(gate):
    assert executor.unknown_commands_in([_LOAD, _USE]) == ["json_dumps"]
    gate.allow_packages("json")
    assert executor.unknown_commands_in([_LOAD, _USE, ["nope"], ["os_getcwd"]]) == [
        "nope", "os_getcwd"]
    assert executor.unknown_commands_in([_USE, _LOAD]) == ["json_dumps"]


def test_cli_validate_and_run_agree(gate, tmp_path, capsys):
    from je_auto_control.cli import main
    script = tmp_path / "script.json"
    script.write_text(json.dumps([_LOAD, _USE]), encoding="utf-8")
    assert main(["validate", str(script)]) == 1
    assert main(["run", str(script)]) == 1
    assert "unknown command 'json_dumps'" in capsys.readouterr().err
    assert main(["run", str(script), "--allow-package", "json"]) == 0
    assert '"[1, 2]"' in capsys.readouterr().out
    assert main(["validate", str(script)]) == 0     # the gate is still open in this process


def test_the_validators_are_unchanged_without_a_gate():
    known = {"AC_add_package_to_executor"}
    with pytest.raises(AutoControlActionException, match="unknown command 'json_dumps'"):
        validate_actions([_LOAD, _USE], known)
    assert unknown_command_names([_LOAD, _USE], known) == ["json_dumps"]
    validate_actions([_LOAD, _USE], known, loadable=lambda package: package == "json")
    assert unknown_command_names(
        [_LOAD, _USE], known, loadable=lambda package: False) == ["json_dumps"]


def test_would_allow_imports_nothing():
    from unittest.mock import patch
    manager = PackageManager()
    manager.allowed_packages = {"json"}
    with patch.object(package_manager_class.importlib, "import_module") as importer:
        assert manager.would_allow("json") is True
        assert manager.would_allow("json.decoder") is True
        assert manager.would_allow("jsonx") is False
        assert manager.would_allow("os") is False
        for not_a_name in ("", "os; rm", "${package}", 3, None, ["json"]):
            assert manager.would_allow(not_a_name) is False
        manager.set_allow_arbitrary_packages(True)
        assert manager.would_allow("os") is True
        assert manager.would_allow("os; rm") is False
        importer.assert_not_called()


# --- the sample project in the repository root ------------------------------

@pytest.mark.parametrize("name", ["keyword1.json", "keyword2.json"])
def test_the_repository_sample_runs_without_opening_the_gate(name):
    """The checked-in sample is what ``--create_project`` writes: no package load."""
    from je_auto_control.utils.project.template import template_keyword
    actions = json.loads((_REPO / "AutoControl" / "keyword" / name).read_text(encoding="utf-8"))
    validate_actions(actions, executor.known_commands())
    assert not [action for action in actions if action[0].startswith("AC_add_package")]
    template = {"keyword1.json": template_keyword.template_keyword_1,
                "keyword2.json": template_keyword.template_keyword_2}[name]
    assert actions == json.loads(json.dumps(template))
