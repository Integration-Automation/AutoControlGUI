"""The package gate in front of AC_add_package_to_executor (workspace X-12)."""
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


def test_unconfigured_gate_still_loads_but_warns():
    manager = _manager()
    with pytest.warns(DeprecationWarning, match="not on the allowlist"):
        manager.add_package_to_executor("json")
    assert "json_dumps" in manager.executor.event_dict


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
    executor.set_allow_arbitrary_packages(False)
    executor.allow_packages("my_company_helpers")
    assert shared_gate.allow_arbitrary_packages is False
    assert "my_company_helpers" in shared_gate.allowed_packages


def test_no_action_command_can_open_the_gate():
    for name in executor.known_commands():
        assert "allow_arbitrary_packages" not in name
        assert "allow_packages" not in name


def test_refusal_reaches_the_action_record(shared_gate):
    executor.set_allow_arbitrary_packages(False)
    record = executor.execute_action([["AC_add_package_to_executor", {"package": "os"}]])
    assert any("not allowed" in str(value) for value in record.values())
    assert "os_system" not in executor.event_dict
