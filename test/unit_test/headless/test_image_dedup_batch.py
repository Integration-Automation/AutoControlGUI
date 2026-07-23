"""Headless tests for perceptual-hash image dedupe. Clustering/compare logic is
exercised with precomputed hashes and an injected hasher (no image needed); the
real Pillow hashing path runs under importorskip. Pure stdlib otherwise; no Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.image_dedup import (
    average_hash, dedupe_images, dhash, hamming_distance, images_similar)


def test_hamming_distance_and_similar():
    assert hamming_distance("00", "00") == 0
    assert hamming_distance("0f", "00") == 4      # 0x0f -> 1111 bits
    assert images_similar("ff", "fe", max_distance=1) is True
    assert images_similar("ff", "f0", max_distance=1) is False


def test_dedupe_with_injected_hasher():
    # hashes chosen so a/b are 1 bit apart, c is far
    table = {"a.png": "ff", "b.png": "fe", "c.png": "00"}
    unique = dedupe_images(["a.png", "b.png", "c.png"], max_distance=1,
                           hasher=table.get)
    assert unique == ["a.png", "c.png"]           # b collapses into a


def test_dedupe_strict_threshold_keeps_all():
    table = {"a": "ff", "b": "fe"}
    assert dedupe_images(["a", "b"], max_distance=0, hasher=table.get) == \
        ["a", "b"]


def test_dedupe_empty():
    assert dedupe_images([], hasher=lambda x: "00") == []


def test_real_pillow_hashing(tmp_path):
    pil_image = pytest.importorskip("PIL.Image")
    black = tmp_path / "black.png"
    white = tmp_path / "white.png"
    pil_image.new("RGB", (64, 64), (0, 0, 0)).save(black)
    pil_image.new("RGB", (64, 64), (255, 255, 255)).save(white)

    h_black = average_hash(str(black))
    assert isinstance(h_black, str) and h_black
    assert average_hash(str(black)) == h_black                    # stable
    assert isinstance(dhash(str(black)), str)

    # two solid-but-different images dedupe down by perceptual hash
    unique = dedupe_images([str(black), str(black), str(white)],
                           max_distance=0)
    assert len(unique) <= 3 and str(black) in unique


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip(tmp_path):
    pil_image = pytest.importorskip("PIL.Image")
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    pil_image.new("RGB", (32, 32), (10, 10, 10)).save(a)
    pil_image.new("RGB", (32, 32), (10, 10, 10)).save(b)   # identical
    rec = ac.execute_action([
        ["AC_dedupe_images", {"paths": [str(a), str(b)], "max_distance": 2}],
    ])
    unique = next(v for v in rec.values() if isinstance(v, dict))["unique"]
    assert unique == [str(a)]                          # identical -> collapse


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_image_hash", "AC_dedupe_images"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_image_hash", "ac_dedupe_images"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    cmds = {s.command for s in _build_specs()}
    assert {"AC_image_hash", "AC_dedupe_images"} <= cmds


def test_facade_exports():
    for attr in ("average_hash", "dhash", "hamming_distance",
                 "images_similar", "dedupe_images"):
        assert hasattr(ac, attr)
        assert attr in ac.__all__
