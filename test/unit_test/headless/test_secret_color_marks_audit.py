"""Secret references, colour matching, mark labels, JSON contracts and config schemas.

AC_resolve_ref returned secret:// values into executor records and MCP
results; colour matches came back region-local, matched blank screens and ran
a quadratic NMS; labels of negative marks were clamped to 0 and crowded ones
stacked off-screen; snapshots never matched their own payload and a string
ignore skipped everything; config schemas accepted null, lists and typo'd
types, and read "false" as required.
"""
import math
from decimal import Decimal

import numpy as np
import pytest

from je_auto_control.utils.executor.action_executor import execute_action
from je_auto_control.utils.secret_ref import SecretRefError, resolve_ref


# --- secret references -----------------------------------------------------------------------------

def test_secret_refs_never_enter_an_executor_record():
    record = execute_action([["AC_resolve_ref", {"ref": "secret://api-key"}],
                             ["AC_resolve_refs", {"obj": {"db": {"password": "secret://db"}}}]])
    values = list(record.values())
    assert all("SecretRefError" in str(value) for value in values)
    assert "not returned" in str(values[0])


def test_env_refs_still_resolve_and_the_python_api_still_reads_secrets(monkeypatch):
    monkeypatch.setenv("AC_AUDIT_BASE_URL", "http://127.0.0.1:9")  # NOSONAR never contacted
    record = execute_action([["AC_resolve_ref", {"ref": "env://AC_AUDIT_BASE_URL"}]])
    assert "http://127.0.0.1:9" in str(record)  # NOSONAR never contacted
    assert resolve_ref("secret://k", secret_resolver=lambda name: "fake-" + name) == "fake-k"


@pytest.mark.parametrize("call", [
    lambda: resolve_ref(5),
    lambda: resolve_ref("file://a\0b"),
    lambda: resolve_ref("secret://missing", secret_resolver=None),
])
def test_bad_refs_are_secret_ref_errors(call, monkeypatch):
    from je_auto_control.utils.governance import default_broker
    monkeypatch.setattr(default_broker, "_resolver", lambda name: {"k": "v"}[name], raising=False)
    with pytest.raises(SecretRefError):
        call()


# --- colour matching ---------------------------------------------------------------------------------

def _plus(colour):
    glyph = np.full((20, 20, 3), 255, dtype=np.uint8)
    glyph[8:12, :] = colour
    glyph[:, 8:12] = colour
    return glyph


def test_a_region_match_is_in_screen_coordinates(monkeypatch):
    from PIL import Image

    from je_auto_control.utils.color_match import match_color, match_color_all
    from je_auto_control.utils.color_region import color_region
    frame = np.full((160, 200, 3), 255, dtype=np.uint8)
    frame[30:50, 20:40] = _plus((255, 0, 0))
    monkeypatch.setattr("je_auto_control.utils.cv2_utils.region_capture.grab_screen_region",
                        lambda region=None: Image.fromarray(frame))
    assert color_region._grab_rgb([500, 300, 700, 460]).shape == (160, 200, 3)
    match = match_color(_plus((255, 0, 0)), region=[500, 300, 700, 460], min_score=0.9)
    assert (match.x, match.y) == (520, 330)
    assert [(hit.x, hit.y) for hit in match_color_all(_plus((255, 0, 0)), region=[500, 300, 700, 460],
                                                      min_score=0.9)] == [(520, 330)]


def test_a_blank_screen_does_not_match_a_coloured_glyph():
    from je_auto_control.utils.color_match import match_color, match_color_all
    blank = np.full((240, 320, 3), 255, dtype=np.uint8)
    assert match_color(_plus((255, 0, 0)), haystack=blank) is None
    assert match_color_all(_plus((255, 0, 0)), haystack=blank, min_score=0.0, max_results=5) != []  # capped, not hung
    assert match_color_all(_plus((255, 0, 0)), haystack=blank) == []


def test_an_image_opencv_cannot_convert_is_a_framework_error():
    from je_auto_control.utils.color_match import match_color
    from je_auto_control.utils.exception.exceptions import AutoControlException
    with pytest.raises(AutoControlException):
        match_color(_plus((255, 0, 0)), haystack=np.zeros((40, 40, 3), np.float64))


# --- mark labels -------------------------------------------------------------------------------------------

def _overlap(a, b):
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def test_a_label_stays_beside_a_mark_on_another_monitor():
    from je_auto_control.utils.marks_layout.marks_layout import place_labels
    [placed] = place_labels([{"id": 1, "bbox": [-500, 300, 80, 30]}])
    assert placed["label"][0] == -500 and abs(placed["label"][1] - 300) <= 20
    [top] = place_labels([{"id": 2, "bbox": [10, 0, 80, 30]}])
    assert top["label"][1] >= 0


def test_crowded_labels_stay_in_bounds_and_apart():
    from je_auto_control.utils.marks_layout.marks_layout import place_labels
    labels = [entry["label"] for entry in
              place_labels([{"id": n, "bbox": [1890, 1000, 30, 20]} for n in range(12)], bounds=(1920, 1080))]
    assert all(0 <= x and x + w <= 1920 and 0 <= y and y + h <= 1080 for x, y, w, h in labels)
    assert not any(_overlap(a, b) for index, a in enumerate(labels) for b in labels[index + 1:])


def test_marks_in_every_geometry_shape_are_placed():
    from je_auto_control.utils.marks_layout.marks_layout import place_labels
    assert len(place_labels([{"id": 1, "bounds": [10, 10, 40, 20]},
                             {"id": 2, "x": 100, "y": 10, "width": 40, "height": 20}])) == 2


# --- JSON contracts and config schemas -------------------------------------------------------------------------

def test_a_snapshot_matches_its_own_payload(tmp_path):
    from je_auto_control.utils.json_contract.json_contract import match_json, snapshot_json
    for index, payload in enumerate(({"point": (10, 20)}, {1: "one"}, {"ratio": math.nan})):
        path = tmp_path / f"snap{index}.json"
        assert snapshot_json(payload, str(path)) and snapshot_json(payload, str(path))
    assert match_json((1, 2), [1, 2]).ok
    assert not match_json({"a": 1, "b": 2}, {"a": 9, "b": 8}, ignore="$.ts").ok


@pytest.mark.parametrize("spec, config", [
    ({"name": {"type": "str", "required": True}}, {"name": None}),
    ({"name": {"type": "str", "required": True}}, {"name": [1, 2]}),
    ({"count": {"type": "int"}}, {"count": Decimal("2.9")}),
])
def test_config_values_that_are_not_their_type_are_errors(spec, config):
    from je_auto_control.utils.config_schema import validate_config
    assert validate_config(spec, config, environ={})["ok"] is False


def test_config_type_typos_fail_and_false_is_not_required():
    from je_auto_control.utils.config_schema import validate_config
    with pytest.raises(ValueError, match="unknown type"):
        validate_config({"port": {"type": "integer"}}, {"port": "abc"}, environ={})
    assert validate_config({"port": {"type": "int", "required": "false"}}, {}, environ={})["ok"] is True
