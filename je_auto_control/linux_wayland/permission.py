"""Typed permission failures that cannot be mistaken for missing input tools."""
from je_auto_control.utils.exception.exceptions import AutoControlException, AutoControlScreenException


class WaylandInputUnavailable(AutoControlException):
    """The authorized input transport cannot perform the requested operation."""

    state = "unsupported"
    capability = "input"


class WaylandDependencyRequired(WaylandInputUnavailable):
    """Native input is missing dependencies; CLI requires explicit selection."""

    state = "needs_dependency"


class WaylandPermissionRequired(AutoControlScreenException):
    """Stop control after cancellation/revocation; explicit retry is required.

    Deliberately excludes RuntimeError: optional-library fallback boundaries
    must not catch a refusal of authorization and switch input transports.
    """

    state = "needs_permission"

    def __init__(self, capability: str, reason: str) -> None:
        self.capability = capability
        self.reason = reason
        super().__init__(
            f"{reason}. Control stopped; explicitly retry portal authorization "
            "or configure JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli."
            if capability == "input" else
            f"{reason}. Explicitly retry screenshot authorization."
        )
