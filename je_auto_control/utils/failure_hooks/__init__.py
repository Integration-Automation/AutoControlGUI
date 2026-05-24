"""Failure → ticket automation: open a Jira / Linear / GitHub issue
when a scheduled run, trigger, or REST job fails.

Public surface::

    from je_auto_control import (
        FailureReport, GitHubBackend, JiraBackend, LinearBackend,
        TicketResult, default_failure_hook_manager,
    )

    default_failure_hook_manager.register(
        GitHubBackend(owner="acme", repo="ops",
                       token=os.environ["GH_TOKEN"]),
    )

    # In a scheduler / trigger error handler:
    default_failure_hook_manager.fire(FailureReport(
        source="scheduler", source_id="nightly-smoke",
        script_path="scripts/smoke.json",
        error_text=str(exc),
        screenshot_path="/tmp/failure.png",
    ))
"""
from je_auto_control.utils.failure_hooks.backends import (
    GitHubBackend, JiraBackend, LinearBackend, TicketBackend,
)
from je_auto_control.utils.failure_hooks.manager import (
    FailureHookManager, default_failure_hook_manager,
)
from je_auto_control.utils.failure_hooks.report import (
    FailureReport, TicketResult,
)


__all__ = [
    "FailureHookManager", "FailureReport", "GitHubBackend",
    "JiraBackend", "LinearBackend", "TicketBackend", "TicketResult",
    "default_failure_hook_manager",
]
