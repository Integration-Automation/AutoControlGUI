"""Keep every test run's package log out of the shared per-user file.

The package logs to ``~/.je_auto_control/logs/AutoControlGUI.log``, a file
every process on the account appends to, including a production bot. The
``pytest11`` plugin imports the package before this file runs, but the handler
reads ``JE_AUTOCONTROL_LOG_FILE`` only when it first opens the file, so setting
it here still redirects the whole run. Overwritten rather than defaulted: a
value inherited from the shell may well be that production file.
"""
import os
import tempfile
from pathlib import Path

os.environ["JE_AUTOCONTROL_LOG_FILE"] = str(
    Path(tempfile.gettempdir()) / "je_auto_control_pytest" / "AutoControlGUI.log")
