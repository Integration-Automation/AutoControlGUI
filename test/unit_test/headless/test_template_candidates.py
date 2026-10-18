"""Reviewed template revisions use fixed pixels and preserve intervening file edits."""
import json
from pathlib import Path

import pytest

import je_auto_control as ac

FIXTURES = Path(__file__).resolve().parents[3] / "benchmarks/self_healing/fixtures"


@pytest.fixture(autouse=True)
def no_device_or_backend(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("template candidates must not capture, click or choose a network backend")

    monkeypatch.setattr("je_auto_control.utils.monitor_layout.logical_frame._load_image_grab", forbidden)
    monkeypatch.setattr("je_auto_control.utils.cv2_utils.region_capture.grab_screen_region", forbidden)
    monkeypatch.setattr("je_auto_control.utils.self_healing.locator._click_at", forbidden)
    monkeypatch.setattr("je_auto_control.utils.vision.vlm_api.get_backend", forbidden)


@pytest.fixture
def revision_files(tmp_path):
    target, bundle, dataset = (tmp_path / name for name in ("template.png", "candidate.json", "dataset.json"))
    target.write_bytes((FIXTURES / "old.png").read_bytes())
    for name in ("frame_new.png", "absent.png"):
        (tmp_path / name).write_bytes((FIXTURES / name).read_bytes())
    dataset.write_text(json.dumps({"schema_version": 1, "samples": [
        {"id": "hit", "frame": "frame_new.png", "expected_box": [20, 16, 37, 29]},
        {"id": "miss", "frame": "absent.png", "expected_miss": True},
        {"id": "unknown", "frame": "frame_new.png"},
    ]}), encoding="utf-8")
    return target, bundle, dataset


def create(files):
    target, bundle, _ = files
    return ac.create_template_candidate(target, (FIXTURES / "new.png").read_bytes(), bundle, threshold=0.99)


def test_create_preview_and_verify_leave_active_template_unchanged(revision_files):
    target, bundle, dataset = revision_files
    original = target.read_bytes()
    created = create(revision_files)
    preview = ac.preview_template_candidate(bundle)
    verified = ac.verify_template_candidate(bundle, dataset)
    assert target.read_bytes() == original
    assert created.revision == preview.state.revision == verified.state.revision
    assert preview.state.state == "original" and preview.original_png and preview.candidate_png
    assert verified.eligible and verified.reasons == ()
    assert verified.comparison.to_dict()["versions"]["candidate"]["unknown"] == 1


def test_accept_and_revert_are_explicit_exact_and_repeatable(revision_files):
    target, bundle, dataset = revision_files
    original = target.read_bytes()
    created = create(revision_files)
    accepted = ac.accept_template_candidate(bundle, dataset, created.revision)
    assert accepted.changed and accepted.state.state == "candidate"
    assert target.read_bytes() == (FIXTURES / "new.png").read_bytes()
    assert not ac.accept_template_candidate(bundle, dataset, created.revision).changed
    reverted = ac.revert_template_candidate(bundle, created.revision)
    assert reverted.changed and reverted.state.state == "original"
    assert target.read_bytes() == original
    assert not ac.revert_template_candidate(bundle, created.revision).changed


@pytest.mark.parametrize("operation", ["accept", "revert"])
def test_intervening_edits_are_not_overwritten(revision_files, operation):
    target, bundle, dataset = revision_files
    created = create(revision_files)
    replacement = (FIXTURES / "absent.png").read_bytes()
    target.write_bytes(replacement)
    with pytest.raises(ac.TemplateRevisionConflict):
        if operation == "accept":
            ac.accept_template_candidate(bundle, dataset, created.revision)
        else:
            ac.revert_template_candidate(bundle, created.revision)
    assert target.read_bytes() == replacement


def test_candidate_must_be_the_revision_the_reviewer_selected(revision_files):
    target, bundle, dataset = revision_files
    original = target.read_bytes()
    create(revision_files)
    with pytest.raises(ac.TemplateRevisionConflict):
        ac.accept_template_candidate(bundle, dataset, "0" * 64)
    assert target.read_bytes() == original


def test_bundle_cannot_overwrite_existing_artifact_or_active_template(revision_files):
    target, bundle, _ = revision_files
    created = create(revision_files)
    with pytest.raises(ac.TemplateRevisionConflict):
        create(revision_files)
    assert ac.preview_template_candidate(bundle).state.revision == created.revision
    with pytest.raises(ac.TemplateRevisionError):
        ac.create_template_candidate(target, (FIXTURES / "new.png").read_bytes(), target)


@pytest.mark.parametrize("labels", ["unknown", "positive_only", "miss_only", "wrong"])
def test_accept_requires_labelled_positive_and_negative_regression_evidence(revision_files, labels):
    target, bundle, dataset = revision_files
    created = create(revision_files)
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    if labels == "unknown":
        payload["samples"] = [{"id": "unlabelled", "frame": "frame_new.png"}]
    elif labels == "positive_only":
        payload["samples"] = payload["samples"][:1]
    elif labels == "miss_only":
        payload["samples"] = payload["samples"][1:2]
    else:
        payload["samples"][0]["expected_box"] = [0, 0, 5, 5]
    dataset.write_text(json.dumps(payload), encoding="utf-8")
    verified = ac.verify_template_candidate(bundle, dataset)
    assert not verified.eligible and verified.reasons
    original = target.read_bytes()
    with pytest.raises(ac.TemplateRevisionError):
        ac.accept_template_candidate(bundle, dataset, created.revision)
    assert target.read_bytes() == original


def test_atomic_replace_failure_keeps_original_and_bundle(revision_files, monkeypatch):
    target, bundle, dataset = revision_files
    created = create(revision_files)
    original = target.read_bytes()

    def fail(*_args):
        raise OSError("controlled replacement failure")

    monkeypatch.setattr("je_auto_control.utils.json_store.json_store._replace", fail)
    with pytest.raises(OSError):
        ac.accept_template_candidate(bundle, dataset, created.revision)
    assert target.read_bytes() == original and bundle.exists()


@pytest.mark.parametrize("fmt,suffix", [("JPEG", ".jpg"), ("BMP", ".bmp")])
def test_target_encoding_is_preserved_and_revert_restores_original_bytes(revision_files, fmt, suffix):
    import io
    from PIL import Image
    target, bundle, _ = revision_files
    target = target.with_suffix(suffix)
    with Image.open(FIXTURES / "old.png") as image:
        image.save(target, format=fmt)
    original = target.read_bytes()
    created = ac.create_template_candidate(target, (FIXTURES / "new.png").read_bytes(), bundle)
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    import base64
    candidate_bytes = base64.b64decode(payload["candidate"])
    with Image.open(io.BytesIO(candidate_bytes)) as image:
        assert image.format == fmt
    # Simulate the exact accepted file to isolate rollback of an encoded target.
    target.write_bytes(candidate_bytes)
    assert ac.revert_template_candidate(bundle, created.revision).changed
    assert target.read_bytes() == original


def test_cancellation_before_commit_preserves_template(revision_files):
    from concurrent.futures import CancelledError
    target, bundle, dataset = revision_files
    created = create(revision_files)
    signal = CancelledError("controlled cancellation")
    original = target.read_bytes()

    def cancel(_count):
        raise signal

    with pytest.raises(CancelledError) as caught:
        ac.accept_template_candidate(bundle, dataset, created.revision, observer=cancel)
    assert caught.value is signal and target.read_bytes() == original


def test_loaded_frame_root_revocation_prevents_acceptance(revision_files):
    from je_auto_control.utils.path_guard import PathPolicy, PathNotAllowedError
    target, bundle, dataset = revision_files
    created = create(revision_files)
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    payload["samples"] = payload["samples"][:2]
    dataset.write_text(json.dumps(payload), encoding="utf-8")
    policy = PathPolicy(use_client_roots=True)
    policy.set_client_roots([target.parent])
    calls = 0

    def revoke(_count):
        nonlocal calls
        calls += 1
        if calls == 5:
            policy.set_client_roots([target, bundle, dataset])

    original = target.read_bytes()
    with pytest.raises(PathNotAllowedError):
        ac.accept_template_candidate(bundle, dataset, created.revision, path_policy=policy, observer=revoke)
    assert target.read_bytes() == original


def test_tampered_bundle_and_unknown_fields_are_rejected(revision_files):
    target, bundle, _ = revision_files
    create(revision_files)
    body = json.loads(bundle.read_text(encoding="utf-8"))
    body["original_hash"] = "0" * 64
    bundle.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ac.TemplateRevisionError):
        ac.preview_template_candidate(bundle)
    body["unexpected"] = True
    bundle.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ac.TemplateRevisionError):
        ac.preview_template_candidate(bundle)
    assert target.read_bytes() == (FIXTURES / "old.png").read_bytes()


def test_two_reviewers_cannot_both_replace_the_same_original(revision_files):
    from concurrent.futures import ThreadPoolExecutor
    target, bundle, dataset = revision_files
    first = create(revision_files)
    other = bundle.with_name("other.json")
    second = ac.create_template_candidate(target, (FIXTURES / "new.png").read_bytes(), other, threshold=0.98)

    def accept(path, revision):
        return ac.accept_template_candidate(path, dataset, revision).changed

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda pair: accept(*pair), [(bundle, first.revision), (other, second.revision)]))
    # Both candidates contain identical promoted bytes; one actual replace and one unchanged retry.
    assert sorted(results) == [False, True]


def test_different_concurrent_candidates_cannot_overwrite_each_other(revision_files):
    import io
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from PIL import Image
    target, bundle, dataset = revision_files
    first = create(revision_files)
    with Image.open(FIXTURES / "new.png") as image:
        with image.convert("RGB") as changed:
            red, green, blue = changed.getpixel((0, 0))
            changed.putpixel((0, 0), ((red + 1) % 256, green, blue))
            output = io.BytesIO()
            changed.save(output, format="PNG")
    other = bundle.with_name("other.json")
    second = ac.create_template_candidate(target, output.getvalue(), other, threshold=0.9)
    barrier = threading.Barrier(2)

    def accept(path, revision):
        reached = False

        def checkpoint(count):
            nonlocal reached
            if count == 6 and not reached:
                reached = True
                barrier.wait(5)

        try:
            return ac.accept_template_candidate(path, dataset, revision, observer=checkpoint).changed
        except ac.TemplateRevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(accept, path, state.revision) for path, state in ((bundle, first), (other, second))]
        results = [future.result() for future in futures]
    assert results.count(True) == results.count("conflict") == 1


def test_cancel_at_commit_lock_boundary_does_not_write(revision_files, monkeypatch):
    from concurrent.futures import CancelledError
    from contextlib import contextmanager
    from je_auto_control.utils.json_store.json_store import _file_lock
    target, bundle, dataset = revision_files
    created = create(revision_files)
    original = target.read_bytes()
    locked = False

    @contextmanager
    def lock(path):
        nonlocal locked
        with _file_lock(path):
            locked = True
            yield

    def checkpoint(_count):
        if locked:
            raise CancelledError("cancelled while waiting to commit")

    monkeypatch.setattr("je_auto_control.utils.self_healing.template_candidates._file_lock", lock)
    with pytest.raises(CancelledError):
        ac.accept_template_candidate(bundle, dataset, created.revision, observer=checkpoint)
    assert target.read_bytes() == original


@pytest.mark.parametrize("operation", ["accept", "revert"])
def test_bundle_changed_at_final_checkpoint_cannot_commit(revision_files, monkeypatch, operation):
    from contextlib import contextmanager
    from je_auto_control.utils.json_store.json_store import _file_lock
    target, bundle, dataset = revision_files
    created = create(revision_files)
    if operation == "revert":
        ac.accept_template_candidate(bundle, dataset, created.revision)
    before = target.read_bytes()
    locked = False

    @contextmanager
    def lock(path):
        nonlocal locked
        with _file_lock(path):
            locked = True
            yield

    def checkpoint(_count):
        if locked:
            payload = json.loads(bundle.read_text(encoding="utf-8"))
            payload["threshold"] = 0.8
            bundle.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr("je_auto_control.utils.self_healing.template_candidates._file_lock", lock)
    with pytest.raises(ac.TemplateRevisionConflict):
        if operation == "accept":
            ac.accept_template_candidate(bundle, dataset, created.revision, observer=checkpoint)
        else:
            ac.revert_template_candidate(bundle, created.revision, observer=checkpoint)
    assert target.read_bytes() == before
