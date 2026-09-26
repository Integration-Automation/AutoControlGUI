"""8-bit matching, scale sweeps, sub-pixel centres, rbac saves and records, bundle redaction, rubrics, gesture cleanup.

16-bit and float images raised ``cv2.error`` or read as flat; one scale that
could not be scored aborted a sweep and a NumPy array of scales raised; the
sub-pixel centre was half a pixel right; rbac changed users before saving
them and handed out records a caller could edit; the failure bundle wrote
secrets through ``repr`` and tuple actions; a malformed rubric passed with a
perfect score; an aborted drag dropped at its target; a click with no point
clicked (0, 0).
"""
import json
import types
import zipfile

import numpy as np
import pytest



def _scene(dtype=np.uint8, scale=1):
    rng = np.random.default_rng(3)
    haystack = (rng.random((120, 160)) * 255).astype(np.float64)
    if dtype == np.uint16:
        haystack = haystack * 257
    elif dtype == np.float32:
        haystack = haystack / 255
    haystack = haystack.astype(dtype) if dtype != np.float32 else haystack.astype(np.float32)
    return haystack, haystack[20:45, 30:55].copy()


@pytest.mark.parametrize("dtype", [np.uint16, np.float32, np.float64])
def test_sixteen_bit_and_float_images_match_in_eight_bits(dtype):
    from je_auto_control.utils.scale_detect import detect_scale
    from je_auto_control.utils.subpixel_match import match_subpixel
    haystack, template = _scene(dtype)
    match = match_subpixel(template, haystack=haystack)
    assert (match.x, match.y) == (30, 20)
    assert abs(match.cx - 42.0) < 0.05          # (w - 1) / 2 for w = 25: the centre column
    assert detect_scale(template, haystack, scales=np.linspace(1.0, 2.0, 5))["scale"] == 1.0


def test_a_scale_that_cannot_be_scored_is_skipped_and_bad_scales_refused():
    from je_auto_control.utils.scale_detect import scale_sweep
    haystack, template = _scene()
    assert [entry["scale"] for entry in scale_sweep(template, haystack, scales=[1.0, 1e6])] == [1.0]
    with pytest.raises(ValueError):
        scale_sweep(template, haystack, scales=[float("nan")])


def test_rbac_changes_only_what_it_saved(tmp_path, monkeypatch):
    from je_auto_control.utils.rbac import users as users_module
    from je_auto_control.utils.rbac.users import UserAuthError, UserStore
    unreadable = tmp_path / "broken.json"
    unreadable.write_text("{not json", encoding="utf-8")
    store = UserStore(unreadable)
    with pytest.raises(UserAuthError):
        store.add_user(user_id="mallory", display_name="m", role="admin", token="tok-mallory")
    with pytest.raises(UserAuthError):
        store.authenticate("tok-mallory")

    store = UserStore(tmp_path / "users.json")
    token = store.add_user(user_id="bob", display_name="b", role="viewer", token="tok-bob")

    def disk_full(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(users_module, "atomic_write_text", disk_full)
    with pytest.raises(UserAuthError):
        store.set_role("bob", "admin")
    with pytest.raises(UserAuthError):
        store.rotate_token("bob")
    assert store.authenticate(token).role == "viewer"


def test_rbac_hands_out_records_a_caller_cannot_edit(tmp_path):
    import dataclasses

    from je_auto_control.utils.rbac.users import UserStore
    store = UserStore(tmp_path / "users.json")
    token = store.add_user(user_id="eve", display_name="e", role="viewer", tags=["a"])
    record = store.authenticate(token)
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.role = "admin"
    record.tags.append("admin")
    assert store.get("eve").tags == ["a"]
    assert store.list_users()[0].role == "viewer"


def test_the_failure_bundle_masks_nested_mappings_tuples_and_reprs(tmp_path):
    from je_auto_control.utils.failure_bundle import FailureBundleOptions, create_failure_bundle

    class Conn:
        def __repr__(self):
            return "Conn(dsn='db', password='hunter2')"

    path = create_failure_bundle(
        str(tmp_path / "bundle.zip"), error="boom",
        options=FailureBundleOptions(screenshot=False, diagnostics=False),
        context={"headers": types.MappingProxyType({"Authorization": "Bearer abc"}),
                 "last_action": ("AC_secret_set", "db", "hunter2"), "conn": Conn()},
        events=[{"step": 1, "cfg": types.MappingProxyType({"password": "hunter2"})}])
    with zipfile.ZipFile(path) as archive:
        manifest = archive.read("manifest.json").decode("utf-8")
    assert "hunter2" not in manifest and "Bearer abc" not in manifest
    assert json.loads(manifest)["context"]["last_action"][0] == "AC_secret_set"


@pytest.mark.parametrize("rubric", [[{"forbidden_actions": ["delete_all"]}], {"forbiden_actions": ["delete_all"]},
                                    "forbidden_actions"])
def test_a_malformed_rubric_is_refused(rubric):
    from je_auto_control.utils.trajectory_eval import evaluate_trajectory
    with pytest.raises(ValueError):
        evaluate_trajectory([{"action": "delete_all"}], rubric)
    assert not evaluate_trajectory([{"action": "delete_all"}], {"forbidden_actions": ["delete_all"]})["passed"]


def test_an_aborted_drag_releases_where_it_stopped():
    from je_auto_control.utils.mouse_path import drag_path
    events = []

    def sink(event):
        events.append(event)
        if event["op"] == "move" and event["x"] == 25:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        drag_path([[0, 0], [100, 0], [100, 100]], per_segment_steps=4, sink=sink)
    assert events[-1] == {"op": "release", "button": "mouse_left"}
    completed = []
    drag_path([[0, 0], [10, 0]], per_segment_steps=2, sink=completed.append)
    assert completed[-1] == {"op": "release", "button": "mouse_left", "x": 10, "y": 0}


def test_a_step_without_a_point_acts_where_the_pointer_is(monkeypatch):
    from je_auto_control.utils.input_macro import run_sequence
    from je_auto_control.wrapper import auto_control_mouse
    calls = []
    monkeypatch.setattr(auto_control_mouse, "set_mouse_position", lambda x, y: calls.append(("move", x, y)))
    monkeypatch.setattr(auto_control_mouse, "click_mouse",
                        lambda button, x=None, y=None: calls.append(("click", button, x, y)))
    run_sequence([{"op": "click", "button": "mouse_right"}])
    assert calls == [("click", "mouse_right", None, None)]
    with pytest.raises(ValueError):
        run_sequence([{"op": "move"}])
    slept = []
    run_sequence([{"op": "wait", "ms": -5}], sink=lambda _event: None, sleep=slept.append)
    assert slept == [0.0]
    with pytest.raises(ValueError):
        run_sequence([{"op": "wait", "ms": float("inf")}], sink=lambda _event: None, sleep=slept.append)


def test_a_non_finite_replay_gap_is_refused():
    from je_auto_control.utils.input_macro import replay_timeline
    with pytest.raises(ValueError):
        replay_timeline([{"op": "key", "key": "a", "delta_ms": float("inf")}],
                        sink=lambda _event: None, sleep=lambda _seconds: None)
