"""Self-consistency over multiple grounding proposals for one target."""
from je_auto_control.utils.grounding_consensus.grounding_consensus import (
    ConsensusResult, consensus_element, consensus_point, is_confident,
)

__all__ = [
    "ConsensusResult", "consensus_point", "consensus_element", "is_confident",
]
