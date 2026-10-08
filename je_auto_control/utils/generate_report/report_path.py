"""Where a report file is written.

TestPioneer starts a runner with ``TEST_PIONEER_ARTIFACT_DIR`` set to the
directory that run's output belongs in. A report asked for under a relative
name goes there, so the workflow does not have to say which files to collect.
Outside TestPioneer nothing changes.
"""
import os
from pathlib import Path

from je_auto_control.utils.json_store.json_store import atomic_write_text
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

# Set by TestPioneer for every runner it starts, in a child process and in-process alike.
ARTIFACT_DIR_VARIABLE: str = "TEST_PIONEER_ARTIFACT_DIR"


def report_path(name: str) -> str:
    """Return where the report called ``name`` is written.

    With ``TEST_PIONEER_ARTIFACT_DIR`` set, a relative ``name`` is placed below
    that directory and the folders it needs are created. ``name`` is returned
    as given when the variable is not set, when ``name`` is absolute, when it
    would leave the directory (``../x``), and when the folders cannot be
    created.
    """
    directory = os.environ.get(ARTIFACT_DIR_VARIABLE, "").strip()
    if not directory or Path(name).is_absolute():
        return name
    base = Path(directory).resolve()
    target = (base / name).resolve()
    if base not in target.parents:
        return name
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        autocontrol_logger.error(
            "report_path: %r, the artifact directory is not usable: %r", name, error)
        return name
    return str(target)


def write_report(name: str, text: str) -> str:
    """Write the report called ``name`` atomically; return where it went.

    The file is also noted on the action journal's running step, when a
    journal is started, so the step that produced a report names it.
    """
    path = report_path(name)
    atomic_write_text(path, text)
    from je_auto_control.utils.action_journal.recorder import note_artifact
    note_artifact("report", path=os.path.abspath(path))
    return path
