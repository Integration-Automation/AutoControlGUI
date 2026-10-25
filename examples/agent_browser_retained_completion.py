"""Review an already stopped browser task through the existing service API.

Importing this example starts nothing. Preview first; after reviewing its exact
verification_spec and snapshot, explicitly call complete_reviewed with a note.
An original retained context must still exist; this never opens a replacement page.
"""
from je_auto_control import finish_agent_task, manage_agent_recovery


def preview_retained(task_id: str) -> dict:
    """Inspect the exact source effects and current original-context availability."""
    return manage_agent_recovery("preview_completion", {"task_id": task_id})


def complete_reviewed(task_id: str, snapshot: str, note: str) -> dict:
    """Create and finish the explicitly reviewed no-action verifier on the original context."""
    child = manage_agent_recovery("create_completion", {"task_id": task_id, "snapshot": snapshot, "note": note})
    return finish_agent_task(child["task_id"])
