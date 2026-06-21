"""Headless tests for near-duplicate text detection. Pure stdlib, no Qt."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.utils.near_dup import (
    hamming_distance, minhash_signature, minhash_similarity, near_duplicates,
    simhash,
)


def test_simhash_deterministic_and_identical():
    a = simhash("the quick brown fox jumps")
    assert a == simhash("the quick brown fox jumps")    # deterministic
    assert hamming_distance(a, a) == 0


def test_near_texts_have_small_distance():
    a = simhash("the quick brown fox jumps over the lazy dog")
    b = simhash("the quick brown fox jumps over the lazy dogs")
    far = simhash("completely unrelated sentence about databases")
    assert hamming_distance(a, b) < hamming_distance(a, far)


def test_near_duplicates_clusters():
    texts = [
        "the cat sat on the mat",
        "the cat sat on the mat today",      # near-dup of #0
        "quantum chromodynamics lecture",    # unrelated
    ]
    clusters = near_duplicates(texts, max_distance=12)
    # every index appears exactly once across clusters (partition)
    assert sorted(i for group in clusters for i in group) == [0, 1, 2]
    # 0 and 1 land together, 2 separate
    group_of = {i: gi for gi, group in enumerate(clusters) for i in group}
    assert group_of[0] == group_of[1] and group_of[2] != group_of[0]


def test_minhash_similarity():
    sig_a = minhash_signature("the quick brown fox")
    sig_b = minhash_signature("the quick brown fox")
    assert minhash_similarity(sig_a, sig_b) == pytest.approx(1.0)
    sig_c = minhash_signature("entirely different words here now")
    assert minhash_similarity(sig_a, sig_c) < 1.0
    assert minhash_similarity([], [1]) == pytest.approx(0.0)


def test_hamming_distance():
    assert hamming_distance(0b1010, 0b1001) == 2


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    rec = ac.execute_action([["AC_simhash", {"text": "hello world"}]])
    value = next(v for v in rec.values() if isinstance(v, dict))["simhash"]
    assert isinstance(value, int)
    texts = json.dumps(["the cat sat", "the cat sat now", "zzz"])
    rec2 = ac.execute_action([[
        "AC_near_duplicates", {"texts": texts, "max_distance": 8}]])
    clusters = next(v for v in rec2.values() if isinstance(v, dict))["clusters"]
    assert sorted(i for g in clusters for i in g) == [0, 1, 2]


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_simhash", "AC_near_duplicates"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_simhash", "ac_near_duplicates"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_simhash", "AC_near_duplicates"} <= specs


def test_facade_exports():
    # hamming_distance is exported by image_dedup (identical int semantics)
    for attr in ("simhash", "near_duplicates", "minhash_signature",
                 "minhash_similarity"):
        assert hasattr(ac, attr) and attr in ac.__all__
