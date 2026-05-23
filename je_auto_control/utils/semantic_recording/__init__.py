"""Phase 6.4: enrich raw recordings with semantic anchors.

The built-in recorder produces raw events: ``mouse_press at (245, 380)``
that depend on the exact pixel position of a button. Move the window,
DPI-scale the screen, or replay on a different host and the recording
is brittle.

This module post-processes a recording: for every click, it samples
the accessibility tree (and optionally a VLM) to figure out *which
button / field / link* was hit, and writes an ``anchor`` payload onto
the action. Phase 6.7 (replay-anywhere) consumes that anchor at replay
time to re-locate the element instead of trusting the raw coordinate.

Usage::

    from je_auto_control.utils.semantic_recording import enrich_recording
    enriched = enrich_recording(raw_actions)

The enrichment is best-effort: failures keep the raw action with no
anchor so replay falls back to the coordinate path.
"""
from je_auto_control.utils.semantic_recording.enrich import (
    AnchorResolver, enrich_action, enrich_recording,
)
from je_auto_control.utils.semantic_recording.replay import (
    AnchorLocator, relocate_action, relocate_recording,
)
from je_auto_control.utils.semantic_recording.self_healing import (
    ReplayResult, SelfHealingReplayer, StepResult, self_healing_replay,
)

__all__ = [
    "AnchorResolver", "enrich_action", "enrich_recording",
    "AnchorLocator", "relocate_action", "relocate_recording",
    "SelfHealingReplayer", "ReplayResult", "StepResult",
    "self_healing_replay",
]
