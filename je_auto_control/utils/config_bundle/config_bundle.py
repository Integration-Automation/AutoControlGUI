"""Single-file export / import of AutoControl's user configuration.

Bundle format (a single JSON document)::

    {
      "manifest": {
        "version": 1,
        "exported_at": "2026-04-27T...",
        "platform": "Windows-11-...",
        "source_root": "/home/me/.je_auto_control"
      },
      "files": {
        "admin_hosts.json": {"format": "json", "content": {...}},
        "address_book.json": {"format": "json", "content": {...}},
        "remote_host_id":     {"format": "text", "content": "AC1234567"},
        ...
      }
    }

Files in the allowlist that don't exist on disk simply don't appear in
``files`` — the importer treats absence as "leave that file alone on the
target", not "delete it".

Import is **non-destructive**: any file we are about to overwrite is
first renamed to ``<name>.bak.<unix_ts>`` so the user can roll back.
The audit log (``audit.db``) is intentionally NOT in the allowlist —
it's a tamper-evident log, not config. Replacing it from a bundle
would defeat the chain.
"""
from __future__ import annotations

import json
import os
import platform
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


BUNDLE_VERSION = 1


# Allowlist of relative paths we know how to round-trip. Each entry maps
# to a parser hint:
#   "json"  → load as JSON, embed the parsed object
#   "text"  → embed the file body as a UTF-8 string
_ALLOWLIST: Dict[str, str] = {
    "admin_hosts.json": "json",
    "address_book.json": "json",
    "trusted_viewers.json": "json",
    "known_hosts.json": "json",
    "host_service.json": "json",
    "remote_host_id": "text",
    "viewer_id": "text",
    "host_fingerprint": "text",
}


class ConfigBundleError(Exception):
    """Raised when bundle parsing or writing fails in a recoverable way."""


@dataclass
class ImportReport:
    """Result of an import operation."""

    written: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    backups: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def default_bundle_root() -> Path:
    """``~/.je_auto_control`` — where the per-user config lives."""
    return Path(os.path.expanduser("~")) / ".je_auto_control"


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------


class ConfigBundleExporter:
    """Read every allowlisted file in ``root`` and produce a bundle dict."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = Path(root) if root is not None else default_bundle_root()

    def build(self) -> Dict[str, Any]:
        files: Dict[str, Dict[str, Any]] = {}
        for relative, fmt in _ALLOWLIST.items():
            entry = self._read_one(self._root / relative, fmt)
            if entry is not None:
                files[relative] = entry
        return {
            "manifest": self._manifest(),
            "files": files,
        }

    def _manifest(self) -> Dict[str, Any]:
        return {
            "version": BUNDLE_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "source_root": str(self._root),
        }

    def _read_one(self, path: Path, fmt: str) -> Optional[Dict[str, Any]]:
        if not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            autocontrol_logger.warning(
                "config bundle export %s: %r", path, error,
            )
            return None
        if fmt == "json":
            try:
                content = json.loads(text)
            except ValueError as error:
                autocontrol_logger.warning(
                    "config bundle export %s: invalid JSON: %r", path, error,
                )
                return None
            return {"format": "json", "content": content}
        return {"format": "text", "content": text}


def export_config_bundle(root: Optional[Path] = None) -> Dict[str, Any]:
    """Convenience wrapper around :class:`ConfigBundleExporter`."""
    return ConfigBundleExporter(root=root).build()


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


class ConfigBundleImporter:
    """Validate a bundle dict, then write its contents back to ``root``.

    Existing files are renamed to ``<name>.bak.<unix_ts>`` before being
    overwritten. Files not in the bundle are left alone.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = Path(root) if root is not None else default_bundle_root()

    def apply(self, bundle: Any, *, dry_run: bool = False) -> ImportReport:
        manifest, files = self._validate(bundle)
        report = ImportReport()
        if not dry_run:
            self._root.mkdir(parents=True, exist_ok=True)
        backup_stamp = int(time.time())
        for relative, entry in files.items():
            self._apply_one(
                relative=relative, entry=entry,
                report=report, dry_run=dry_run,
                backup_stamp=backup_stamp,
            )
        autocontrol_logger.info(
            "config bundle import: wrote %d, skipped %d, manifest version %s",
            len(report.written), len(report.skipped),
            manifest.get("version"),
        )
        return report

    def _validate(self, bundle: Any) -> tuple:
        if not isinstance(bundle, dict):
            raise ConfigBundleError("bundle must be a JSON object")
        manifest = bundle.get("manifest")
        files = bundle.get("files")
        if not isinstance(manifest, dict):
            raise ConfigBundleError("bundle.manifest is missing or invalid")
        if not isinstance(files, dict):
            raise ConfigBundleError("bundle.files is missing or invalid")
        try:
            version = int(manifest.get("version", 0))
        except (TypeError, ValueError) as error:
            raise ConfigBundleError(
                f"bundle.manifest.version is not an int: {error}",
            ) from error
        if version != BUNDLE_VERSION:
            raise ConfigBundleError(
                f"unsupported bundle version {version!r}; "
                f"this build understands {BUNDLE_VERSION}",
            )
        return manifest, files

    def _apply_one(self, *, relative: str, entry: Any,
                   report: ImportReport, dry_run: bool,
                   backup_stamp: int) -> None:
        # Reject anything not in the allowlist OR anything that tries to
        # escape the root via path traversal.
        if relative not in _ALLOWLIST:
            report.skipped.append(relative)
            autocontrol_logger.warning(
                "config bundle import: skip unknown file %r", relative,
            )
            return
        if not isinstance(entry, dict):
            report.skipped.append(relative)
            return
        target = (self._root / relative).resolve()
        try:
            target.relative_to(self._root.resolve())
        except ValueError:
            # Path traversal attempt; refuse silently in the report.
            report.skipped.append(relative)
            return
        try:
            text = self._render_entry(_ALLOWLIST[relative], entry)
        except ConfigBundleError as error:
            autocontrol_logger.warning(
                "config bundle import %s: %r", relative, error,
            )
            report.skipped.append(relative)
            return
        if dry_run:
            report.written.append(relative)
            return
        self._write_with_backup(
            target=target, body=text,
            relative=relative, report=report, backup_stamp=backup_stamp,
        )

    def _render_entry(self, fmt: str, entry: Dict[str, Any]) -> str:
        declared_format = entry.get("format")
        if declared_format != fmt:
            raise ConfigBundleError(
                f"format mismatch: bundle says {declared_format!r}, "
                f"allowlist says {fmt!r}",
            )
        if fmt == "json":
            return json.dumps(
                entry.get("content"), ensure_ascii=False, indent=2,
            )
        content = entry.get("content")
        if not isinstance(content, str):
            raise ConfigBundleError("text entry content must be a string")
        return content

    def _write_with_backup(self, *, target: Path, body: str,
                           relative: str, report: ImportReport,
                           backup_stamp: int) -> None:
        if target.exists():
            backup_path = target.with_name(
                f"{target.name}.bak.{backup_stamp}",
            )
            try:
                target.replace(backup_path)
                report.backups[relative] = str(backup_path.name)
            except OSError as error:
                autocontrol_logger.warning(
                    "config bundle backup %s: %r", target, error,
                )
                report.skipped.append(relative)
                return
        try:
            target.write_text(body, encoding="utf-8")
        except OSError as error:
            autocontrol_logger.warning(
                "config bundle write %s: %r", target, error,
            )
            report.skipped.append(relative)
            return
        report.written.append(relative)


def import_config_bundle(bundle: Any,
                         root: Optional[Path] = None,
                         *, dry_run: bool = False) -> ImportReport:
    """Convenience wrapper around :class:`ConfigBundleImporter`."""
    return ConfigBundleImporter(root=root).apply(bundle, dry_run=dry_run)


__all__ = [
    "BUNDLE_VERSION", "ConfigBundleError", "ConfigBundleExporter",
    "ConfigBundleImporter", "ImportReport", "default_bundle_root",
    "export_config_bundle", "import_config_bundle",
]
