"""Names the examples had to import from inside the package are on the facade."""
import subprocess
import sys

import pytest

import je_auto_control as ac

_NAMES = (
    "only_run_id", "write_candidate", "check_thresholds", "format_comparison",
    "LocateRequest", "AuthorisationLedger", "AuthorisationState",
    "ACTION_JOURNAL_SCHEMA_VERSION", "HEAL_EVENT_SCHEMA_VERSION",
    "HEALING_DATASET_SCHEMA_VERSION",
    "note_artifact", "note_secret_value", "carry_step", "check_robot_structure",
    "RobotStructureError", "vlm_strategy", "ModelUsage", "UsageMeter",
    "build_verifier", "HealVerificationError", "VERIFY_TYPES", "comparison_rows",
    "COMPARISON_COLUMNS",
)


@pytest.mark.parametrize("name", _NAMES)
def test_the_name_is_exported(name):
    assert name in ac.__all__, name
    assert getattr(ac, name) is not None


def test_no_name_is_listed_twice():
    assert len(ac.__all__) == len(set(ac.__all__))


def test_the_exports_are_the_objects_the_package_defines():
    from je_auto_control.linux_wayland import authorisation
    from je_auto_control.utils.action_journal import events
    from je_auto_control.utils.codegen import journal_import
    from je_auto_control.utils.self_healing import eval_strategies, evaluation, heal_log
    assert ac.only_run_id is journal_import.only_run_id
    assert ac.write_candidate is journal_import.write_candidate
    assert ac.check_thresholds is evaluation.check_thresholds
    assert ac.format_comparison is evaluation.format_comparison
    assert ac.LocateRequest is evaluation.LocateRequest
    assert ac.AuthorisationLedger is authorisation.AuthorisationLedger
    assert ac.AuthorisationState is authorisation.AuthorisationState
    assert ac.ACTION_JOURNAL_SCHEMA_VERSION == events.SCHEMA_VERSION == 1
    assert ac.HEAL_EVENT_SCHEMA_VERSION == heal_log.HEAL_EVENT_SCHEMA_VERSION
    assert ac.HEALING_DATASET_SCHEMA_VERSION == eval_strategies.DATASET_SCHEMA_VERSION


def test_importing_the_facade_still_loads_no_qt():
    code = ("import sys, je_auto_control; "
            "sys.exit(1 if any('PySide6' in name for name in sys.modules) else 0)")
    done = subprocess.run([sys.executable, "-c", code], check=False, timeout=120)  # nosec B603  # nosemgrep  # reason: fixed argv, this interpreter
    assert done.returncode == 0
