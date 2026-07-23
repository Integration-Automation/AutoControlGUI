"""Create a self-contained ZIP for diagnosing failed automation runs.

Collection is deliberately best-effort: failure diagnostics must still be
created when screen capture, an optional backend, or the diagnostics runner
itself is broken.  Text and structured values are redacted before they enter
the archive and arbitrary attachments are opt-in.
"""
from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import time
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from je_auto_control.utils.config_redaction import (
    redact_config,
    redact_secret_text,
)


@dataclass(frozen=True)
class FailureBundleOptions:
    """Controls potentially sensitive or expensive bundle collectors."""

    screenshot: bool = True
    diagnostics: bool = True
    log_path: str | None = None
    log_tail_bytes: int = 256_000
    attachments: tuple[str, ...] = ()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2,
                      sort_keys=True, default=repr).encode("utf-8")


def _safe_name(path: Path, used: set[str]) -> str:
    base = path.name or "attachment"
    candidate, index = base, 2
    while candidate in used:
        candidate = f"{path.stem}-{index}{path.suffix}"
        index += 1
    used.add(candidate)
    return candidate


def _read_log_tail(path: Path, limit: int) -> str:
    with path.open("rb") as handle:
        if path.stat().st_size > limit:
            handle.seek(-limit, os.SEEK_END)
        data = handle.read()
    return redact_secret_text(data.decode("utf-8", errors="replace"))


def _collect_diagnostics(archive: zipfile.ZipFile,
                         failures: list[dict[str, str]]) -> None:
    try:
        from je_auto_control.utils.diagnostics import run_diagnostics
        archive.writestr("diagnostics.json",
                         _json_bytes(run_diagnostics().to_dict()))
    except Exception as exc:  # diagnostics are best-effort
        failures.append({"collector": "diagnostics", "error": repr(exc)})


def _collect_screenshot(archive: zipfile.ZipFile,
                        failures: list[dict[str, str]]) -> None:
    try:
        from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as image_file:
            image_path = image_file.name
        try:
            pil_screenshot().save(image_path, format="PNG")
            archive.write(image_path, "screenshot.png")
        finally:
            Path(image_path).unlink(missing_ok=True)
    except Exception as exc:  # headless and locked sessions are valid
        failures.append({"collector": "screenshot", "error": repr(exc)})


def _collect_log(archive: zipfile.ZipFile, opts: FailureBundleOptions,
                 failures: list[dict[str, str]]) -> None:
    try:
        archive.writestr("logs/tail.log", _read_log_tail(
            Path(opts.log_path or "").expanduser().resolve(),
            max(1, opts.log_tail_bytes)))
    except Exception as exc:
        failures.append({"collector": "log", "error": repr(exc)})


def _collect_attachments(archive: zipfile.ZipFile, opts: FailureBundleOptions,
                         failures: list[dict[str, str]]) -> None:
    used: set[str] = set()
    for raw_path in opts.attachments:
        try:
            path = Path(raw_path).expanduser().resolve(strict=True)
            if not path.is_file():
                raise ValueError("attachment is not a regular file")
            archive.write(path, f"attachments/{_safe_name(path, used)}")
        except Exception as exc:
            failures.append({"collector": "attachment", "error": repr(exc)})


def _collect_all(archive: zipfile.ZipFile, opts: FailureBundleOptions,
                 failures: list[dict[str, str]]) -> None:
    if opts.diagnostics:
        _collect_diagnostics(archive, failures)
    if opts.screenshot:
        _collect_screenshot(archive, failures)
    if opts.log_path:
        _collect_log(archive, opts, failures)
    _collect_attachments(archive, opts, failures)


def create_failure_bundle(
    output_path: str | os.PathLike[str],
    *,
    error: BaseException | str | None = None,
    context: Mapping[str, Any] | None = None,
    events: Iterable[Mapping[str, Any]] = (),
    options: FailureBundleOptions | None = None,
) -> str:
    """Write an atomic, redacted diagnostic ZIP and return its real path."""
    opts = options or FailureBundleOptions()
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    failures: list[dict[str, str]] = []
    manifest = {
        "schema": "autocontrol.failure-bundle/v1",
        "created_at_unix": time.time(),
        "error": None if error is None else redact_secret_text(str(error)),
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "executable": Path(sys.executable).name,
        },
        "context": redact_config(dict(context or {})),
        "events": redact_config(list(events)),
        "collector_failures": failures,
    }

    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.",
                                     suffix=".tmp", dir=str(target.parent))
    os.close(fd)
    try:
        with zipfile.ZipFile(temp_name, "w", zipfile.ZIP_DEFLATED) as archive:
            _collect_all(archive, opts, failures)
            archive.writestr("manifest.json", _json_bytes(manifest))
        os.replace(temp_name, target)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return str(target)


@contextmanager
def failure_bundle_on_error(
    output_path: str | os.PathLike[str],
    *,
    context: Mapping[str, Any] | None = None,
    events: Iterable[Mapping[str, Any]] = (),
    options: FailureBundleOptions | None = None,
):
    """Create a bundle when the wrapped block raises, then re-raise it."""
    try:
        yield
    except BaseException as error:
        create_failure_bundle(output_path, error=error, context=context,
                              events=events, options=options)
        raise
