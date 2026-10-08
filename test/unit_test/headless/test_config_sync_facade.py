"""What a config-sync script needs is on the package facade.

Writing the offline example for config sync meant reaching into
``je_auto_control.utils.config_sync`` for the errors a caller has to catch,
the adapters it has to build and the function that runs a sync -- names the
facade did not carry.
"""
import subprocess
import sys

import pytest

import je_auto_control as ac
from je_auto_control.utils import config_sync

_NAMES = (
    "RevisionConflictError", "ConfigStoreError", "OperationMismatchError",
    "ScriptSyncAdapter", "LocatorSyncAdapter", "HotkeySyncAdapter", "TriggerSyncAdapter",
    "AddressBookSyncAdapter", "run_sync", "DirectoryAssetTransport", "HttpAssetTransport",
    "BlobStore",
)


@pytest.mark.parametrize("name", _NAMES)
def test_the_name_is_exported_and_is_the_config_sync_object(name):
    assert name in ac.__all__
    assert getattr(ac, name) is getattr(config_sync, name)


def test_the_wire_version_has_a_name_that_says_whose_it_is():
    # A bare WIRE_VERSION on the facade would not say which wire.
    assert "CONFIG_SYNC_WIRE_VERSION" in ac.__all__
    assert ac.CONFIG_SYNC_WIRE_VERSION == config_sync.WIRE_VERSION == 2
    assert "WIRE_VERSION" not in ac.__all__


def test_no_name_is_listed_twice():
    assert len(ac.__all__) == len(set(ac.__all__))


def test_the_errors_can_be_caught_as_the_family():
    assert issubclass(ac.RevisionConflictError, ac.ConfigStoreError)
    assert issubclass(ac.ConfigStoreError, ac.ConfigSyncError)
    assert issubclass(ac.OperationMismatchError, ac.ConfigSyncError)


def test_importing_the_facade_still_does_not_import_qt_or_fastapi():
    code = ("import sys, je_auto_control\n"
            "bad = [m for m in sys.modules if m.split('.')[0] in ('PySide6', 'fastapi')]\n"
            "print('loaded', bad)\n")
    done = subprocess.run(  # nosec B603  # nosemgrep  # reason: fixed argv, this interpreter
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=120, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == "loaded []"
