"""Beta passive backend capability API; no consent, capture or input effects."""
from je_auto_control.wrapper.capabilities import (
    BackendContext, CapabilitySnapshot, CapabilityStatus, probe_capabilities,
)

__all__ = ["BackendContext", "CapabilitySnapshot", "CapabilityStatus", "probe_capabilities"]
