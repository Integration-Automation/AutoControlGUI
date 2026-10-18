"""Immutable bounded template revision bundles and content-derived active-file state."""
import base64
import binascii
import json
import os
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from je_auto_control.utils.json_store.json_store import _file_lock, atomic_write_bytes
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.self_healing.evaluation_io import _bounded_path, _read, _unique_object
from je_auto_control.utils.self_healing.frame_locators import TemplateFrameLocator
from je_auto_control.utils.self_healing.template_images import (
    MAX_IMAGE_BYTES, encode_candidate, image_metadata, normalized_png,
)
from je_auto_control.utils.self_healing.template_models import (
    TemplateCandidateState, TemplateRevisionConflict, TemplateRevisionError,
)

_FIELDS = {"schema_version", "target", "original", "candidate", "original_hash", "candidate_hash", "threshold"}


@dataclass(frozen=True)
class TemplateBundle:
    """Validated stored bytes; file state is computed from content, with no mutable sidecar pointer."""

    path: Path
    target: Path
    original: bytes = field(repr=False)
    candidate: bytes = field(repr=False)
    threshold: float
    revision: str

    def state(self, policy: Optional[PathPolicy]) -> TemplateCandidateState:
        """Read bounded target content after rechecking its canonical binding and current roots."""
        target = self.checked_target(policy)
        try:
            current = digest(_read(target, MAX_IMAGE_BYTES))
        except FileNotFoundError:
            current = None
        original, candidate = digest(self.original), digest(self.candidate)
        state: Literal["original", "candidate", "conflict", "missing"]
        state = "missing" if current is None else "original" if current == original else "candidate"
        if current is not None and current not in (original, candidate):
            state = "conflict"
        fmt, size = image_metadata(self.original)
        _, candidate_size = image_metadata(self.candidate)
        return TemplateCandidateState(self.revision, str(self.path), str(self.target), original, candidate,
                                      current, state, fmt, size, candidate_size, threshold=self.threshold)

    def checked_target(self, policy: Optional[PathPolicy]) -> Path:
        """Refuse a target whose canonical path was redirected after review."""
        _check_binding(self.target, policy)
        _check_binding(self.path, policy)
        return self.target

    def check_revision(self, policy: Optional[PathPolicy]) -> None:
        """Recheck the exact previously validated bundle without decoding its pixels again."""
        self.checked_target(policy)
        if digest(_read(self.path, 48 * 1024 * 1024)) != self.revision:
            raise TemplateRevisionConflict("candidate bundle differs from the reviewed revision")


def digest(payload: bytes) -> str:
    """Content identity for file comparison and reviewed bundle revisions."""
    return sha256(payload).hexdigest()


def create_bundle(target_path: str | Path, candidate_png: bytes, bundle_path: str | Path,
                    threshold: float, policy: Optional[PathPolicy],
                    observer: Optional[Callable[[int], None]] = None) -> TemplateBundle:
    """Persist one explicit version artifact without replacing an existing bundle or active template."""
    if observer is not None:
        observer(0)
    target, path = _bounded_path(target_path, policy), _bounded_path(bundle_path, policy)
    if target == path:
        raise TemplateRevisionError("bundle destination must differ from the active template")
    original = _read(target, MAX_IMAGE_BYTES)
    candidate = encode_candidate(original, candidate_png)
    candidate_normalized, _, _ = normalized_png(candidate)
    TemplateFrameLocator(candidate_normalized, threshold)
    if digest(original) == digest(candidate):
        raise TemplateRevisionError("candidate image must differ from the original")
    payload = {"schema_version": 1, "target": str(target), "threshold": threshold,
               "original": base64.b64encode(original).decode("ascii"),
               "candidate": base64.b64encode(candidate).decode("ascii"),
               "original_hash": digest(original), "candidate_hash": digest(candidate)}
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    with _file_lock(path):
        if observer is not None:
            observer(1)
        _check_binding(path, policy)
        _check_binding(target, policy)
        if path.exists():
            raise TemplateRevisionConflict("candidate bundle already exists")
        atomic_write_bytes(path, data)
        with path.open("rb+") as handle:
            os.fsync(handle.fileno())
    return TemplateBundle(path, target, original, candidate, threshold, digest(data))


def _check_binding(path: Path, policy: Optional[PathPolicy]) -> None:
    if _bounded_path(path, policy) != path:
        raise TemplateRevisionConflict("candidate file binding was redirected")


def read_bundle(bundle_path: str | Path, policy: Optional[PathPolicy]) -> TemplateBundle:
    """Validate schema, embedded hashes, formats and every referenced file path."""
    path = _bounded_path(bundle_path, policy)
    data = _read(path, 48 * 1024 * 1024)
    try:
        body = json.loads(data, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError) as error:
        raise TemplateRevisionError("candidate bundle must be UTF-8 JSON") from error
    body = _schema(body)
    target = _target(body["target"], path, policy)
    original, candidate = _images(body)
    normalized, _, _ = normalized_png(candidate)
    threshold = body["threshold"]
    TemplateFrameLocator(normalized, threshold)
    return TemplateBundle(path, target, original, candidate, float(threshold), digest(data))


def _schema(body: object) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) != _FIELDS:
        raise TemplateRevisionError("invalid candidate bundle schema")
    version = body["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise TemplateRevisionError("invalid candidate bundle schema")
    return body


def _target(target_value: object, path: Path, policy: Optional[PathPolicy]) -> Path:
    if not isinstance(target_value, str) or not Path(target_value).is_absolute():
        raise TemplateRevisionError("candidate target must be an absolute path")
    target = _bounded_path(target_value, policy)
    if str(target) != target_value or target == path:
        raise TemplateRevisionConflict("candidate target binding changed")
    return target


def _images(body: dict[str, Any]) -> tuple[bytes, bytes]:
    original, candidate = _image(body["original"]), _image(body["candidate"])
    if digest(original) != body["original_hash"] or digest(candidate) != body["candidate_hash"]:
        raise TemplateRevisionError("candidate bundle image hash mismatch")
    _, fmt, _ = normalized_png(candidate)
    if fmt != normalized_png(original)[1] or digest(original) == digest(candidate):
        raise TemplateRevisionError("candidate format or content is inconsistent")
    return original, candidate


def _image(value: object) -> bytes:
    if not isinstance(value, str) or len(value) > 24 * 1024 * 1024:
        raise TemplateRevisionError("invalid candidate bundle image")
    try:
        result = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as error:
        raise TemplateRevisionError("invalid candidate bundle image encoding") from error
    if not result or len(result) > MAX_IMAGE_BYTES:
        raise TemplateRevisionError("candidate bundle image exceeds 16 MiB")
    return result
