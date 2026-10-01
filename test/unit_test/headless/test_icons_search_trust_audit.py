"""Icons, nested runs, collation, checksums, the IME wait, search, match trust, postconditions, reading flow.

Dark-theme widgets were read inverted and clipped boxes by their requested
size; nested action lists ran on the module's executor, losing a device's
variables; "ß" weighed as one "s"; float and very long checksum input broke;
the IME wait slept past its deadline or spun; TF-IDF dropped a term in every
document and CJK words inside a sentence were unsearchable; a unique ccorr
match read as ambiguous; OCR text never satisfied text_present; match objects
broke the reading order.
"""
import cv2
import numpy as np
import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException


# --- icons ---------------------------------------------------------------------------------------------

def _checkbox(background, ink):
    image = np.full((30, 30), background, np.uint8)
    cv2.rectangle(image, (5, 5), (24, 24), ink, 2)
    return image


def test_a_dark_theme_checkbox_is_a_checkbox():
    from je_auto_control.utils.icon_classify import classify_icon
    assert classify_icon(_checkbox(255, 0), [2, 2, 26, 26])["type"] == "checkbox"
    assert classify_icon(_checkbox(30, 230), [2, 2, 26, 26])["type"] == "checkbox"


def test_a_box_past_the_edge_uses_the_clipped_patch_and_bad_arrays_are_framework_errors():
    from je_auto_control.utils.icon_classify import box_features, classify_icon
    image = _checkbox(255, 0)
    assert box_features(image, [-10, 0, 30, 20])["aspect"] == box_features(image, [0, 0, 20, 20])["aspect"]
    with pytest.raises(AutoControlException):
        classify_icon(image.astype(np.float32), [2, 2, 26, 26])


# --- nested runs on the running executor ------------------------------------------------------------------

def test_a_device_variable_reaches_nested_action_lists():
    from je_auto_control.utils.device_matrix.matrix import run_on_devices
    body = [["AC_circuit_call", {"name": "audit-circuit", "actions": [
        ["AC_set_var", {"name": "id", "value": "${device.serial}"}]]}]]
    report = run_on_devices(body, [{"platform": "android", "serial": "a"},
                                   {"platform": "android", "serial": "b"}])
    assert report.success, report.to_dict()
    with pytest.raises(ValueError, match="index"):
        run_on_devices(body, [{"platform": "android", "serial": "a"}, "emulator-5556"])


# --- collation and checksums ----------------------------------------------------------------------------------

def test_sharp_s_weighs_as_ss_and_is_lowercase():
    from je_auto_control.utils.locale_collation import compare, sort_strings
    assert compare("ß", "ss", strength="primary") == 0
    assert compare("Maß", "MaS") != 0
    assert sort_strings(["Maßa", "Masb"]) == ["Masb", "Maßa"]


def test_checksums_take_whole_floats_and_any_length():
    from je_auto_control.utils.checksum.checksum import (
        luhn_check_digit, luhn_validate, mod97_10_check_digits, mod97_10_validate,
    )
    assert luhn_validate(79927398713.0) is True and luhn_check_digit(7992739871.0) == "3"
    assert mod97_10_validate("1" * 5000) in (True, False)
    assert len(mod97_10_check_digits("1" * 5000)) == 2
    assert mod97_10_validate("3214282912345698765432161182")


# --- the IME wait -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("interval, bound", [(10.0, 1.0), (0.0, 0.05), (-0.1, 0.05)])
def test_the_ime_wait_sleeps_within_its_deadline_and_never_spins(interval, bound):
    from je_auto_control.utils.ime_state.ime_state import wait_for_composition_commit
    now, slept = [0.0], []

    def sleep(seconds):
        slept.append(seconds)
        now[0] += seconds
        if len(slept) > 100:
            raise AssertionError("the wait spun without advancing")

    assert wait_for_composition_commit(reader=lambda: {"composition": "ni"}, timeout_s=1.0, interval_s=interval,
                                       clock=lambda: now[0], sleep=sleep) is False
    assert slept and max(slept) <= 1.0 and len(slept) <= round(1.0 / bound) + 1


# --- search ----------------------------------------------------------------------------------------------------

def test_search_finds_common_terms_cjk_words_and_mixed_ids():
    from je_auto_control.utils.search_index.search_index import SearchIndex, search_documents, tokenize
    assert tokenize("Login failed") == ["login", "failed"]
    assert search_documents({"a": "login failed"}, "login", mode="tfidf")
    assert [hit.doc_id for hit in search_documents({"a": "請先登入系統"}, "登入")] == ["a"]
    assert [hit.doc_id for hit in search_documents({"a": "ログインに失敗しました"}, "ログイン")] == ["a"]
    assert len(SearchIndex.build([(1, "alpha"), ("x", "alpha")]).search("alpha")) == 2


# --- match trust, postconditions, reading flow ---------------------------------------------------------------------

def test_a_unique_ccorr_match_is_not_ambiguous():
    from je_auto_control.utils.match_trust.match_trust import match_with_trust
    ui = np.full((200, 300), 235, np.uint8)
    button = np.full((24, 60), 235, np.uint8)
    cv2.rectangle(button, (1, 1), (58, 22), 180, 1)
    cv2.putText(button, "OK", (20, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 30, 1, cv2.LINE_AA)
    ui[100:124, 150:210] = button
    assert match_with_trust(button, haystack=ui, method="ccorr_normed").is_ambiguous is False


def test_ocr_text_satisfies_a_postcondition():
    from je_auto_control.utils.postcondition.postcondition import check_postcondition
    frame = [{"text": "Saved", "x": 0, "y": 0, "width": 50, "height": 20}]
    assert check_postcondition(frame, {"text_present": "Saved"}).ok


def test_reading_flow_takes_every_element_shape():
    from dataclasses import dataclass

    from je_auto_control.utils.reading_flow.reading_flow import flow_order

    @dataclass
    class Match:
        text: str
        x: int
        y: int
        width: int
        height: int

    for boxes in ([{"text": "A1", "bbox": [0, 0, 40, 20]}, {"text": "B1", "bbox": [100, 0, 40, 20]}],
                  [Match("A1", 0, 0, 40, 20), Match("B1", 100, 0, 40, 20)]):
        assert [box["text"] for box in flow_order(boxes)] == ["A1", "B1"]
