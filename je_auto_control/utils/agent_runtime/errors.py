"""Typed failures for managed tasks, observations and control ownership."""
from je_auto_control.utils.exception.exceptions import AutoControlException


class AgentTaskError(AutoControlException, ValueError):
    """A managed task cannot perform the requested operation."""


class AgentControlBusy(AgentTaskError):
    """Another task still owns the target's input or cleanup."""


class AgentObservationStale(AgentTaskError):
    """No action was dispatched because its observation is missing, expired or changed."""


class AgentHumanReview(AgentTaskError):
    """A dialog or unsaved-content gate requires explicit human review before continuing."""
