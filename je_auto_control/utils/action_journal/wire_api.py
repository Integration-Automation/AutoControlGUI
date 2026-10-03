"""Thin JSON command adapters for journal orchestration."""
from typing import Dict, List, Optional, Union

from je_auto_control.utils.action_journal.events import JSONValue


def record_actions(actions: Union[str, List[object], Dict[str, object]], path: str, *,
                   run_id: Optional[str] = None, raise_on_error: bool = False,
                   device: Optional[str] = None, session: Optional[str] = None) -> Dict[str, JSONValue]:
    """Delegate recording to the full headless journal/history/execution boundary."""
    # pylint: disable-next=import-outside-toplevel  # reason: retain the orchestrator's lazy executor boundary
    from je_auto_control.utils.action_journal.api import execute_journaled
    return execute_journaled(actions, path, run_id=run_id, raise_on_error=raise_on_error,
                             device=device, session=session)
