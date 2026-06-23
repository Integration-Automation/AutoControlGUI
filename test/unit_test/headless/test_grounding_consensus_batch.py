"""Headless tests for grounding self-consistency (pure stdlib)."""
import je_auto_control as ac
from je_auto_control.utils.grounding_consensus import (
    consensus_element, consensus_point, is_confident,
)


def test_majority_cluster_wins():
    # three proposals agree near (100,100); one outlier far away
    candidates = [[100, 100], [104, 98], [97, 103], [500, 400]]
    result = consensus_point(candidates, cluster_radius=24)
    assert result is not None
    assert abs(result.point[0] - 100) <= 5 and abs(result.point[1] - 100) <= 5
    assert result.n_clusters == 2
    assert abs(result.agreement - 0.75) < 1e-9


def test_weights_influence_consensus():
    # the lone heavy-weight proposal outvotes two light ones
    candidates = [[10, 10, 1.0], [12, 9, 1.0], [200, 200, 5.0]]
    result = consensus_point(candidates, cluster_radius=20)
    assert abs(result.point[0] - 200) <= 2


def test_is_confident_threshold():
    strong = consensus_point([[0, 0], [1, 1], [2, 2]])
    assert is_confident(strong, min_agreement=0.6) is True
    split = consensus_point([[0, 0], [500, 500]], cluster_radius=10)
    assert is_confident(split, min_agreement=0.6) is False


def test_consensus_element_votes_nearest():
    elements = [{"x": 0, "y": 0, "width": 20, "height": 20},
                {"x": 200, "y": 0, "width": 20, "height": 20}]
    # two votes near element 0, one near element 1
    winner, agreement = consensus_element([[8, 8], [12, 10], [205, 9]], elements)
    assert winner is elements[0]
    assert abs(agreement - (2 / 3)) < 1e-3   # rounded to 4 dp


def test_empty_inputs():
    assert consensus_point([]) is None
    assert consensus_element([[1, 1]], []) is None
    assert is_confident(None) is False


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_consensus_point", "AC_consensus_element"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_consensus_point", "ac_consensus_element"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_consensus_point", "AC_consensus_element"} <= specs


def test_facade_exports():
    for name in ("consensus_point", "consensus_element", "is_confident",
                 "ConsensusResult"):
        assert hasattr(ac, name) and name in ac.__all__
