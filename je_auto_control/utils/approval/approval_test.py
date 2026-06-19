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
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Union

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


def _paths(name: str, approvals_dir: str, extension: str):
    base = Path(approvals_dir)
    ext = extension.lstrip(".")
    return (base / f"{_safe_name(name)}.approved.{ext}",
            base / f"{name}.received.{ext}")


def _as_bytes(content: Union[str, bytes]) -> bytes:
    return content.encode("utf-8") if isinstance(content, str) else bytes(content)


def verify_artifact(name: str, content: Union[str, bytes],
                    approvals_dir: str = DEFAULT_DIR,
                    extension: str = "txt") -> ApprovalResult:
    """Compare ``content`` to the approved baseline for ``name``.

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
    names = [path.name.split(".received.", 1)[0]
             for path in base.glob("*.received.*")]
    return sorted(names)
