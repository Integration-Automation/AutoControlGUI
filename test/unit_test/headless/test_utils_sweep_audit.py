"""A sweep of less-visited utils subpackages (fakes and synthetic frames only).

Region-local coordinates from three locators; one frame per template vote; a
race in the shared voice router; unit-glued numbers in failure signatures;
delta counts from other frames than the summary; a stale index on removed
elements; no home directory; NaN percentiles; clipped checkboxes; averaged
contrast colours; opaque URL schemes; nameless elements; bridge errors;
mis-cased webhook transports.
"""
import math
import types
from pathlib import Path

import numpy as np
import pytest

from je_auto_control.utils.visual_match import visual_match

_ORIGIN = (1000, 400)


def _with_origin(monkeypatch, frame):
    """Stand in for the screen grab only (a supplied haystack is never grabbed)."""
    calls = []

    def fake(region):
        calls.append(region)
        return frame, _ORIGIN[0], _ORIGIN[1]

    monkeypatch.setattr(visual_match, "_grab_gray_with_origin", fake)
    return calls


def _frame_with_square():
    frame = np.zeros((200, 200), dtype=np.uint8)
    frame[35:55, 55:75] = 255
    frame[40:50, 60:70] = 80
    return frame


# --- screen coordinates ------------------------------------------------------------------------------

def test_a_theme_match_is_in_screen_coordinates(monkeypatch):
    from je_auto_control.utils.theme_normalize.theme_normalize import match_theme
    frame = _frame_with_square()
    _with_origin(monkeypatch, frame)
    match = match_theme(frame[30:60, 50:80].copy(), region=[1000, 400, 200, 200], min_score=0.3)
    assert match is not None and (match["x"], match["y"]) == (1050, 430)


def test_element_proposals_are_in_screen_coordinates(monkeypatch):
    from je_auto_control.utils.element_proposal.element_proposal import propose_elements
    _with_origin(monkeypatch, _frame_with_square())
    proposals = propose_elements(region=[1000, 400, 200, 200], min_area=20)
    assert proposals and all(p["box"][0] >= 1000 and p["box"][1] >= 400 for p in proposals)


def test_barcode_points_are_in_screen_coordinates(monkeypatch):
    from je_auto_control.utils.barcode import barcode
    monkeypatch.setattr(barcode, "_haystack_gray_with_origin",
                        lambda source, region: (np.zeros((10, 10), np.uint8), *_ORIGIN))
    found = barcode.read_barcodes(region=[1000, 400, 10, 10],
                                  decoder=lambda image: [{"text": "1", "type": "EAN_13",
                                                          "points": [[100, 60], [180, 60]]}])
    assert found[0]["points"] == [[1100, 460], [1180, 460]]


def test_an_ensemble_votes_on_one_frame_in_screen_coordinates(monkeypatch):
    from je_auto_control.utils.match_ensemble.match_ensemble import match_ensemble
    grabs = _with_origin(monkeypatch, np.zeros((50, 50), np.uint8))
    monkeypatch.setattr(visual_match, "match_template",
                        lambda template, **kwargs: types.SimpleNamespace(center=[10, 12]))
    import je_auto_control.utils.visual_match as package
    monkeypatch.setattr(package, "match_template", visual_match.match_template)
    result = match_ensemble(["a", "b", "c"], region=[1000, 400, 50, 50])
    assert len(grabs) == 1 and result["point"] == [1010, 412]


# --- the voice router ----------------------------------------------------------------------------------

def test_the_voice_router_matches_the_commands_it_scored(monkeypatch):
    from je_auto_control.utils import fuzzy
    from je_auto_control.utils.voice.voice_router import VoiceRouter
    router = VoiceRouter()
    router.register("delete file", [["AC_delete_everything"]])
    router.register("save file", [["AC_save"]])

    def racing(text, phrases, score_cutoff):
        router.register("delete file", [["AC_delete_everything"]])   # another thread, mid-match
        return (text, 100.0, phrases.index(text))

    monkeypatch.setattr(fuzzy, "fuzzy_best_match", racing)
    assert router.match("save file").phrase == "save file"


# --- text and observations ---------------------------------------------------------------------------------

def test_failure_signatures_ignore_numbers_glued_to_units():
    from je_auto_control.utils.failure_signature.failure_signature import normalize_error
    assert normalize_error("wait_image timed out after 5s") == normalize_error("wait_image timed out after 7s")
    assert normalize_error("step took 1532ms") == normalize_error("step took 1611ms")
    assert "0x<addr>" in normalize_error("object at 0x7ffd1234")


def _el(x, y, role="button", name="", **extra):
    return dict(x=x, y=y, width=40, height=20, role=role, name=name, **extra)


def test_a_removed_element_carries_no_stale_index():
    from je_auto_control.utils.observation_delta.observation_delta import summarize_delta
    text = summarize_delta({"added": [], "changed": [], "removed": [_el(0, 0, name="Cancel", index=0)]})
    assert text.startswith('- button "Cancel"') and "[0]" not in text


def test_delta_counts_come_from_the_summarised_frames():
    from je_auto_control.utils.executor.action_executor import _delta_observation
    label_before = _el(0, 0, role="text", name="Status: idle")
    label_after = _el(0, 0, role="text", name="Status: busy")
    result = _delta_observation([label_before], [label_after])
    assert result["summary"] == "" and result["changed"] == 0


# --- no home directory ------------------------------------------------------------------------------------

def _no_home(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(Path, "home", staticmethod(refuse))
    monkeypatch.setattr(Path, "expanduser", lambda self: refuse() if str(self).startswith("~") else self)
    monkeypatch.delenv("JE_AUTOCONTROL_LOG_FILE", raising=False)


def test_the_log_file_falls_back_to_the_temp_directory_without_a_home(monkeypatch):
    import tempfile

    from je_auto_control.utils.logging.logging_instance import default_log_file
    _no_home(monkeypatch)
    assert str(default_log_file()).startswith(tempfile.gettempdir())


def test_the_path_guard_reports_a_missing_home_as_its_own_error(monkeypatch, tmp_path):
    from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError, validate_path
    _no_home(monkeypatch)
    monkeypatch.chdir(tmp_path)
    assert validate_path("out.json") == Path(tmp_path, "out.json").resolve()
    with pytest.raises(PathNotAllowedError):
        validate_path("~/out.json")


# --- numbers and pixels -----------------------------------------------------------------------------------

def test_infinite_samples_give_the_longest_timeout_not_the_shortest():
    from je_auto_control.utils.adaptive_timeout.adaptive_timeout import recommend_timeout
    from je_auto_control.utils.stats.stats import percentile
    assert percentile([2.0, math.inf, math.inf], 95) == math.inf
    assert recommend_timeout([math.inf, math.inf, 5.0]) == 60.0


def test_a_checkbox_partly_off_the_frame_is_read():
    from je_auto_control.utils.form_fields.form_fields import checkbox_state
    frame = np.full((50, 50), 255, np.uint8)
    frame[0:10, 0:8] = 0
    assert checkbox_state(frame, {"x": -2, "y": -1, "width": 10, "height": 11}) == "checked"


def test_contrast_uses_the_dominant_colours_not_their_means():
    from je_auto_control.utils.contrast_map.contrast_map import dominant_pair
    pixels = [[255, 255, 255]] * 400 + [[0x76, 0x76, 0x76]] * 100 + [[0xC0, 0xC0, 0xC0]] * 60
    pair = dominant_pair(pixels)
    assert pair["foreground"] == [0x76, 0x76, 0x76] and pair["background"] == [255, 255, 255]


# --- small contracts --------------------------------------------------------------------------------------

@pytest.mark.parametrize("target", ["ms-settings:display", "javascript:alert(1)", "search-ms:query=x"])
def test_an_opaque_scheme_off_the_allow_list_is_refused(target):
    from je_auto_control.utils.shell_open.shell_open import plan_open
    with pytest.raises(ValueError, match="scheme"):
        plan_open(target)


def test_a_drive_letter_is_still_a_path():
    from je_auto_control.utils.shell_open.shell_open import plan_open
    assert plan_open("C:\\Reports\\q3.pdf")["kind"] == "file"


def test_a_nameless_element_is_not_named_none():
    from je_auto_control.utils.element_scoring.element_scoring import score_candidates
    nameless, empty = score_candidates([{"name": None}, {"name": ""}], want_name="Done")
    assert nameless.score == empty.score


def test_only_a_parameter_mismatch_is_reported_as_one(monkeypatch):
    from je_auto_control.utils.webrunner_bridge import bridge

    def to_url(url):
        raise TypeError("'NoneType' object is not subscriptable")

    monkeypatch.setattr(bridge, "_executor", lambda: types.SimpleNamespace(event_dict={"WR_to_url": to_url}))
    with pytest.raises(TypeError, match="subscriptable"):
        bridge.run_webrunner_action({"action": "WR_to_url", "params": {"url": "x"}})
    with pytest.raises(bridge.WebRunnerBridgeError, match="rejected params"):
        bridge.run_webrunner_action({"action": "WR_to_url", "params": {"link": "x"}})


def test_webhook_transports_are_case_insensitive_and_checked():
    from je_auto_control.utils.notify_channels.notify_channels import WebhookChannel
    sent = []
    WebhookChannel("u", transport="Discord", poster=lambda url, payload: sent.append(payload) or 204).send("hi")
    assert sent == [{"content": "hi"}]
    with pytest.raises(ValueError, match="transport"):
        WebhookChannel("u", transport="slak")
