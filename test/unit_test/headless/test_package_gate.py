"""The package gate in front of AC_add_package_to_executor (workspace X-12)."""
import json
import os
import subprocess  # nosec B404  # reason: runs this interpreter on a fixed -c snippet
import sys
import types
import warnings
from unittest.mock import patch

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlExecuteActionException
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.package_manager import package_manager_class
from je_auto_control.utils.package_manager.package_manager_class import PackageManager


def _manager() -> PackageManager:
    manager = PackageManager()
    manager.executor = types.SimpleNamespace(event_dict={})
    return manager


@pytest.fixture
def shared_gate():
    manager = package_manager_class.package_manager
    saved = (manager.allow_arbitrary_packages, set(manager.allowed_packages))
    yield manager
    manager.allow_arbitrary_packages, manager.allowed_packages = saved[0], set(saved[1])


ENV = "JE_AUTOCONTROL_ALLOWED_PACKAGES"


@pytest.fixture(autouse=True)
def _no_inherited_allowlist(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)


def test_unconfigured_gate_refuses_before_importing():
    manager = _manager()
    assert manager.allow_arbitrary_packages is False
    with patch.object(package_manager_class.importlib, "import_module") as importer:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            with pytest.raises(AutoControlExecuteActionException) as refused:
                manager.add_package_to_executor("json")
        importer.assert_not_called()
    assert manager.executor.event_dict == {}
    # The message names every way to allow the package.
    for way in (ENV, "--allow-package", "executor.allow_packages",
                "executor.set_allow_arbitrary_packages(True)"):
        assert way in str(refused.value)


def test_environment_variable_allowlists_packages_and_submodules(monkeypatch):
    assert package_manager_class.ALLOWED_PACKAGES_ENV == ENV
    monkeypatch.setenv(ENV, " json , ,collections.abc,not a name,")
    manager = _manager()
    assert manager.allowed_packages == {"json", "collections.abc"}
    assert manager.allow_arbitrary_packages is False
    manager.add_package_to_executor("json")
    manager.add_package_to_executor("json.decoder")
    assert "json_dumps" in manager.executor.event_dict
    assert "json.decoder_JSONDecoder" in manager.executor.event_dict
    with pytest.raises(AutoControlExecuteActionException):
        manager.add_package_to_executor("collections")
    with pytest.raises(AutoControlExecuteActionException):
        manager.add_package_to_executor("os")


def test_environment_variable_reaches_the_gate_every_entry_point_shares(tmp_path):
    """The executor and the callback executor register this one instance's methods."""
    from je_auto_control.utils.callback.callback_function_executor import callback_executor
    shared = package_manager_class.package_manager
    for table in (executor.event_dict, callback_executor.event_dict):
        for name in ("AC_add_package_to_executor", "AC_add_package_to_callback_executor"):
            assert table[name].__self__ is shared
    code = ("import json; from je_auto_control.utils.package_manager.package_manager_class "
            "import package_manager as m; "
            "print(json.dumps([sorted(m.allowed_packages), m.allow_arbitrary_packages]))")
    env = dict(os.environ, **{ENV: "time,my_plugins"})
    # The child imports the tree under test, wherever pytest was started from.
    tree = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(package_manager_class.__file__)))))
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [tree, env.get("PYTHONPATH")]))
    done = subprocess.run(  # nosec B603  # nosemgrep  # reason: fixed argv, this interpreter
        [sys.executable, "-c", code], env=env, cwd=tmp_path,
        capture_output=True, text=True, timeout=120, check=True)
    assert json.loads(done.stdout.strip().splitlines()[-1]) == [["my_plugins", "time"], False]


def test_allow_packages_rejects_what_is_not_a_package_name():
    manager = _manager()
    for bad in ("", "os; rm", "a..b", 3):
        with pytest.raises(AutoControlExecuteActionException):
            manager.allow_packages("json", bad)
    assert manager.allowed_packages == set()


def test_cli_run_allow_package_opens_the_gate_for_those_names(shared_gate, tmp_path, capsys):
    from je_auto_control.cli import main
    script = tmp_path / "s.json"
    script.write_text(json.dumps([["AC_add_package_to_executor", {"package": "json"}]]),
                      encoding="utf-8")
    executor.event_dict.pop("json_dumps", None)
    try:
        assert main(["run", str(script)]) == 1
        assert "--allow-package" in capsys.readouterr().out
        assert "json_dumps" not in executor.event_dict
        assert main(["run", str(script), "--allow-package", "json",
                     "--allow-package", "collections"]) == 0
        assert "json_dumps" in executor.event_dict
        assert {"json", "collections"} <= shared_gate.allowed_packages
        assert shared_gate.allow_arbitrary_packages is False
        with pytest.raises(SystemExit):
            main(["run", str(script), "--allow-package", "os;rm"])
    finally:
        for name in [name for name in executor.event_dict if name.startswith("json_")]:
            del executor.event_dict[name]


def test_closed_gate_refuses_before_importing():
    manager = _manager()
    manager.set_allow_arbitrary_packages(False)
    with patch.object(package_manager_class.importlib, "import_module") as importer:
        with pytest.raises(AutoControlExecuteActionException, match="not allowed"):
            manager.add_package_to_executor("os")
        importer.assert_not_called()
    assert manager.executor.event_dict == {}


def test_closed_gate_refuses_the_callback_executor_too():
    manager = PackageManager()
    manager.callback_executor = types.SimpleNamespace(event_dict={})
    manager.set_allow_arbitrary_packages(False)
    with pytest.raises(AutoControlExecuteActionException):
        manager.add_package_to_callback_executor("subprocess")
    assert manager.callback_executor.event_dict == {}


def test_allowlisted_package_and_its_submodules_load_without_warning():
    manager = _manager()
    manager.set_allow_arbitrary_packages(False)
    manager.allow_packages("json")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        manager.add_package_to_executor("json")
        manager.add_package_to_executor("json.decoder")
    assert "json.decoder_JSONDecoder" in manager.executor.event_dict
    with pytest.raises(AutoControlExecuteActionException):
        manager.add_package_to_executor("jsonschema_lookalike")


def test_open_gate_loads_anything_without_warning():
    manager = _manager()
    manager.set_allow_arbitrary_packages(True)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        manager.add_package_to_executor("json")
    assert "json_dumps" in manager.executor.event_dict


def test_executor_configures_the_shared_gate(shared_gate):
    assert shared_gate.allow_arbitrary_packages is False     # the default
    executor.set_allow_arbitrary_packages(True)              # the explicit opt-out
    assert shared_gate.allow_arbitrary_packages is True
    executor.set_allow_arbitrary_packages(False)
    executor.allow_packages("my_company_helpers")
    assert shared_gate.allow_arbitrary_packages is False
    assert "my_company_helpers" in shared_gate.allowed_packages


def test_no_action_command_can_open_the_gate():
    for name in executor.known_commands():
        assert "allow_arbitrary_packages" not in name
        assert "allow_packages" not in name


def test_refusal_reaches_the_action_record(shared_gate):
    record = executor.execute_action([["AC_add_package_to_executor", {"package": "os"}]])
    assert any("not allowed" in str(value) for value in record.values())
    assert "os_system" not in executor.event_dict
