"""TOFU (Trust-On-First-Use) host fingerprint verification.

Each host has a stable random hex string at
``~/.je_auto_control/host_fingerprint`` generated on first run. The host
sends it inside ``auth_ok``; the viewer keeps a known-hosts JSON map of
``host_id -> fingerprint`` and warns the user if the fingerprint changes
between connections.

This is *not* a cryptographic substitute for TLS pinning — the
fingerprint is shared in plaintext over an already-DTLS-encrypted
DataChannel. It catches "the signaling slot was hijacked by a different
machine running a different host" but not a fully-compromised channel.
For production-grade trust, layer in TLS client cert pinning above this.
"""
from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_HOST_FP_PATH = (
    Path(os.path.expanduser("~")) / ".je_auto_control" / "host_fingerprint"
)
_KNOWN_HOSTS_PATH = (
    Path(os.path.expanduser("~")) / ".je_auto_control" / "known_hosts.json"
)


def load_or_create_host_fingerprint(path: Optional[Path] = None) -> str:
    """Return the persisted host fingerprint, creating one on first call."""
    target = Path(path) if path is not None else _HOST_FP_PATH
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8").strip()
            if existing and len(existing) == 64:
                return existing
        except OSError:
            pass
    new_fp = secrets.token_hex(32)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_fp, encoding="utf-8")
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    except OSError as error:
        autocontrol_logger.warning("host_fingerprint persist: %r", error)
    return new_fp


class KnownHosts:
    """Viewer-side persistent map of host_id → fingerprints.

    Stores both an application-layer fingerprint (sent in ``auth_ok`` after
    DTLS handshake — see :func:`load_or_create_host_fingerprint`) and the
    DTLS certificate fingerprint extracted from the SDP. The DTLS one is
    the stronger guard: comparing it before answering blocks an attacker
    that hijacked the signaling slot but holds a different cert.

    Legacy on-disk values (plain strings) are auto-migrated on load to the
    new dict shape ``{"app_fp": "...", "dtls_fp": null}``.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = (Path(path) if path is not None else _KNOWN_HOSTS_PATH)
        self._lock = threading.Lock()
        self._entries: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            autocontrol_logger.warning("known_hosts load: %r", error)
            return
        if not isinstance(data, dict):
            return
        for host_id, value in data.items():
            if not isinstance(host_id, str):
                continue
            if isinstance(value, str):
                self._entries[host_id] = {
                    "app_fp": value, "dtls_fp": None, "last_seen": None,
                }
            elif isinstance(value, dict):
                self._entries[host_id] = {
                    "app_fp": value.get("app_fp") or None,
                    "dtls_fp": value.get("dtls_fp") or None,
                    "last_seen": value.get("last_seen") or None,
                }

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._entries, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            try:
                os.chmod(self._path, 0o600)
            except OSError:
                pass
        except OSError as error:
            autocontrol_logger.warning("known_hosts save: %r", error)

    def fingerprint_for(self, host_id: str) -> Optional[str]:
        """Return the app-layer fingerprint (legacy ``host_fingerprint``)."""
        with self._lock:
            entry = self._entries.get(host_id)
            return entry.get("app_fp") if entry else None

    def dtls_fingerprint_for(self, host_id: str) -> Optional[str]:
        """Return the DTLS certificate fingerprint, if previously stored."""
        with self._lock:
            entry = self._entries.get(host_id)
            return entry.get("dtls_fp") if entry else None

    def remember(self, host_id: str, fingerprint: str) -> None:
        """Store the app-layer fingerprint (preserves any DTLS fp)."""
        with self._lock:
            entry = self._entries.setdefault(
                host_id, {"app_fp": None, "dtls_fp": None, "last_seen": None},
            )
            entry["app_fp"] = fingerprint
            self._save()

    def remember_dtls_fingerprint(self, host_id: str, dtls_fp: str) -> None:
        """Store the DTLS cert fingerprint (preserves any app fp)."""
        with self._lock:
            entry = self._entries.setdefault(
                host_id, {"app_fp": None, "dtls_fp": None, "last_seen": None},
            )
            entry["dtls_fp"] = dtls_fp
            self._save()

    def touch(self, host_id: str) -> None:
        """Update last_seen for ``host_id`` to now (UTC ISO)."""
        with self._lock:
            entry = self._entries.setdefault(
                host_id, {"app_fp": None, "dtls_fp": None, "last_seen": None},
            )
            entry["last_seen"] = datetime.now(timezone.utc).isoformat()
            self._save()

    def last_seen(self, host_id: str) -> Optional[str]:
        with self._lock:
            entry = self._entries.get(host_id)
            return entry.get("last_seen") if entry else None

    def forget(self, host_id: str) -> bool:
        with self._lock:
            removed = self._entries.pop(host_id, None) is not None
            if removed:
                self._save()
        return removed

    def list_entries(self) -> Dict[str, dict]:
        with self._lock:
            return {hid: dict(entry) for hid, entry in self._entries.items()}


_default_known_hosts: Optional[KnownHosts] = None
_default_lock = threading.Lock()


def default_known_hosts() -> KnownHosts:
    global _default_known_hosts
    with _default_lock:
        if _default_known_hosts is None:
            _default_known_hosts = KnownHosts()
        return _default_known_hosts


def fingerprint_for_display(value: str) -> str:
    """Format a 64-char hex fingerprint with colons for readability."""
    if not isinstance(value, str) or len(value) != 64:
        return value or ""
    return ":".join(value[i:i + 4] for i in range(0, 64, 4))


_DTLS_FP_RE = __import__("re").compile(
    r"^a=fingerprint:(?P<algo>[A-Za-z0-9-]+)\s+(?P<hex>[0-9A-Fa-f:]+)\s*$",
    flags=__import__("re").MULTILINE,
)


class FingerprintMismatchError(RuntimeError):
    """Raised when a DTLS fingerprint doesn't match the pinned value."""


def extract_dtls_fingerprint(sdp: str, algorithm: str = "sha-256"
                              ) -> Optional[str]:
    """Pull the first DTLS ``a=fingerprint`` line for ``algorithm`` from SDP.

    Returns the colon-separated hex string (e.g. ``AB:CD:...``), or None if
    no matching line exists. Algorithms compared case-insensitively.
    """
    if not isinstance(sdp, str):
        return None
    target_algo = algorithm.lower()
    for match in _DTLS_FP_RE.finditer(sdp):
        if match.group("algo").lower() == target_algo:
            return match.group("hex").upper()
    return None


def verify_dtls_fingerprint(sdp: str, expected_hex: str,
                             algorithm: str = "sha-256") -> None:
    """Raise :class:`FingerprintMismatchError` if SDP doesn't pin to expected.

    ``expected_hex`` may be in either colon (``AB:CD:...``) or solid
    (``ABCD...``) form; comparison is case-insensitive.
    """
    actual = extract_dtls_fingerprint(sdp, algorithm)
    if actual is None:
        raise FingerprintMismatchError(
            f"no {algorithm} DTLS fingerprint in offer",
        )
    expected_normalized = expected_hex.replace(":", "").upper()
    actual_normalized = actual.replace(":", "").upper()
    if expected_normalized != actual_normalized:
        raise FingerprintMismatchError(
            f"DTLS fingerprint mismatch: expected {expected_normalized[:16]}..., "
            f"got {actual_normalized[:16]}...",
        )


__all__ = [
    "load_or_create_host_fingerprint",
    "KnownHosts", "default_known_hosts",
    "fingerprint_for_display",
    "extract_dtls_fingerprint", "verify_dtls_fingerprint",
    "FingerprintMismatchError",
]
