"""Approval testing — lock an artifact against a human-approved baseline.

The approval-testing workflow (a.k.a. golden-master / snapshot testing) turns
"is this output still correct?" into "does this output still match the version
a human approved?". :func:`verify_artifact` compares produced ``content`` to a
stored ``<name>.approved.<ext>`` baseline:

* match  → the check passes;
* mismatch or missing baseline → the produced bytes are written to
  ``<name>.received.<ext>`` and the check fails, so a reviewer can diff the two
  and, if the change is intended, promote it with :func:`approve_artifact`.

It works for any artifact — rendered text, JSON, OCR output, screenshot bytes —
complementing pixel diffing with a review-gated baseline. Pure standard
library; imports no ``PySide6``.
"""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

DEFAULT_DIR = ".approvals"


@dataclass(frozen=True)
class ApprovalResult:
    """Outcome of :func:`verify_artifact`."""

    name: str
    status: str          # "verified" | "mismatch" | "new"
    match: bool
    approved_path: str
    received_path: str


def _safe_name(name: str) -> str:
    """Reject path-traversal in ``name`` and return it unchanged if safe."""
    if not name or name != os.path.basename(name) or name in (".", ".."):
        raise ValueError(f"unsafe approval name: {name!r}")
    return name


_EXTENSION = re.compile(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*")


def _safe_extension(extension: str) -> str:
    """``extension`` without its leading dot; path separators and ``..`` are refused.

    Only ``name`` was checked, so ``extension="x/../../outside/pwned"`` wrote
    outside ``approvals_dir``.
    """
    ext = str(extension).lstrip(".")
    if not _EXTENSION.fullmatch(ext):
        raise ValueError(f"unsafe approval extension: {extension!r}")
    return ext


def _paths(name: str, approvals_dir: str, extension: str):
    base = Path(approvals_dir)
    ext = _safe_extension(extension)
    return (base / f"{_safe_name(name)}.approved.{ext}",
            base / f"{name}.received.{ext}")


def _as_bytes(content: Any) -> bytes:
    """The artifact's bytes: bytes as-is, text as UTF-8, anything else as sorted JSON.

    ``bytes(3)`` is three NUL bytes and ``bytes([104, 105])`` is ``b"hi"``, so
    a number or a list from an action file was stored as the wrong artifact,
    and a dict raised ``TypeError``.
    """
    if isinstance(content, (bytes, bytearray, memoryview)):
        return bytes(content)
    if isinstance(content, str):
        return content.encode("utf-8")
    return json.dumps(content, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def verify_artifact(name: str, content: Any,
                    approvals_dir: str = DEFAULT_DIR,
                    extension: str = "txt") -> ApprovalResult:
    """Compare ``content`` to the approved baseline for ``name``.

    ``content`` is bytes, text (stored as UTF-8) or any JSON value (stored as
    sorted, indented JSON).

    On match the received file is cleared and ``match`` is ``True``; otherwise
    the produced bytes are written to the received file for review.
    """
    approved, received = _paths(name, approvals_dir, extension)
    produced = _as_bytes(content)
    if approved.is_file() and approved.read_bytes() == produced:
        if received.is_file():
            received.unlink()
        return ApprovalResult(name, "verified", True,
                              str(approved), str(received))
    received.parent.mkdir(parents=True, exist_ok=True)
    received.write_bytes(produced)
    status = "mismatch" if approved.is_file() else "new"
    return ApprovalResult(name, status, False, str(approved), str(received))


def approve_artifact(name: str, approvals_dir: str = DEFAULT_DIR,
                     extension: str = "txt") -> str:
    """Promote the received artifact for ``name`` to be the approved baseline."""
    approved, received = _paths(name, approvals_dir, extension)
    if not received.is_file():
        raise FileNotFoundError(
            f"no received artifact to approve for {name!r}")
    os.replace(received, approved)
    return str(approved)


def pending_artifacts(approvals_dir: str = DEFAULT_DIR) -> List[str]:
    """Return the names of artifacts with a received file awaiting approval."""
    base = Path(approvals_dir)
    if not base.is_dir():
        return []
    # A set: "dup.received.txt" and "dup.received.json" listed "dup" twice.
    return sorted({path.name.split(".received.", 1)[0] for path in base.glob("*.received.*")})
