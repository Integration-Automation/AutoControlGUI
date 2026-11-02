"""Bounded document handoff runs outside the disposable native input helper's process tree."""
from __future__ import annotations

import subprocess  # nosec B404  # reason: fixed internal launcher module and one validated document path
import sys

from je_auto_control.utils.agent_runtime.context import current_operation
from je_auto_control.utils.agent_runtime.errors import AgentTaskError

DOCUMENT_SUFFIXES = frozenset({".txt", ".csv", ".xlsx", ".docx", ".pdf", ".png", ".jpg", ".jpeg"})


def launch_document(path: str) -> bool:
    """Launch a host-validated document, preserving the user's application after task cleanup."""
    operation = current_operation()
    if operation is None:
        raise AgentTaskError("document launch requires an explicitly managed operation")
    operation.checkpoint()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        subprocess.run(  # nosec B603  # reason: private fixed launcher, validated canonical path, no shell
            [sys.executable, "-m", "je_auto_control.utils.agent_runtime.document_launch", path],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=operation.spec.budget.action_seconds, check=True, creationflags=flags,
            start_new_session=sys.platform != "win32")
    except (subprocess.SubprocessError, OSError) as error:
        raise AgentTaskError("document handoff is unconfirmed; inspect the application before retrying") from error
    operation.checkpoint()
    return True


def main() -> None:
    """Perform only the private launcher's literal document handoff; never accept shell arguments."""
    from pathlib import Path
    from je_auto_control.utils.shell_open import open_path
    if len(sys.argv) != 2:
        raise AgentTaskError("document launcher requires one approved path")
    path = Path(sys.argv[1])
    if not path.is_absolute() or path.suffix.lower() not in DOCUMENT_SUFFIXES or not path.is_file():
        raise AgentTaskError("document launcher requires an existing supported document")
    if not open_path(str(path)):
        raise AgentTaskError("document launcher did not confirm handoff")


if __name__ == "__main__":
    main()
