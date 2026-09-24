"""Keep every test run out of the account's real per-user state.

The package keeps its state under ``~/.je_auto_control/`` (the remote desktop
audit chain, address book, quarantine list, run history and its error
screenshots) and logs to ``~/.je_auto_control/logs/AutoControlGUI.log``, a file
every process on the account appends to, including a production bot. Tests
that exercise those stores through their defaults used to write the real ones:
by 2026-09-23 ``artifacts/`` held 419 screenshots from test runs.

So the whole run gets a fresh home directory and its own log file. The
``pytest11`` plugin imports the package before this file runs, which is why
this only works for paths the package resolves when they are used rather than
at import -- ``test_state_paths_follow_home.py`` holds the package to that.
Both variables are overwritten, not defaulted: a value inherited from the shell
may well be the real one.
"""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

_SCRATCH = Path(tempfile.gettempdir()) / "je_auto_control_pytest"
_SCRATCH.mkdir(parents=True, exist_ok=True)
_HOME = Path(tempfile.mkdtemp(prefix="home-", dir=_SCRATCH))
atexit.register(shutil.rmtree, _HOME, ignore_errors=True)

os.environ["HOME"] = str(_HOME)
os.environ["USERPROFILE"] = str(_HOME)
os.environ["JE_AUTOCONTROL_LOG_FILE"] = str(_SCRATCH / "AutoControlGUI.log")
