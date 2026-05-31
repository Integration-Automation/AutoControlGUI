"""Per-device ACL for USB passthrough.

Stored at ``~/.je_auto_control/usb_acl.json`` (mode 0600 on POSIX).
Schema (version 1)::

    {
      "version": 1,
      "default": "deny",
      "rules": [
        {
          "vendor_id": "1050",
          "product_id": "0407",
          "serial": null,            // null matches any serial
          "label": "YubiKey 5",
          "allow": true,
          "prompt_on_open": false
        }
      ]
    }

A rule matches when its ``vendor_id`` and ``product_id`` equal the
request and either ``serial`` is null or matches exactly. The first
matching rule wins. If no rule matches, the file's ``default`` applies
("deny" out of the box).

``UsbAcl.decide(...)`` returns one of three strings:

* ``"allow"`` — let the OPEN proceed without asking.
* ``"deny"`` — refuse the OPEN.
* ``"prompt"`` — defer to the host operator. The session will call
  the ``prompt_callback`` and treat its return value as the decision.

File integrity (open question 8) — RESOLVED in Phase 2d.1
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ACL file is protected by an HMAC-SHA256 signature written to a
sidecar ``<acl>.sig`` file. On load, the signature is verified against
the file bytes; a mismatch makes the ACL fail closed (default-deny,
``integrity_ok`` False) so a process that silently rewrites the JSON
cannot grant itself access without also forging the signature.

The signing key is pluggable so deployments can derive it from a
platform keychain: pass ``hmac_key=<bytes>`` to the constructor. When
no key is supplied, a 32-byte random key is generated once and stored
next to the ACL as ``<acl>.key`` (mode ``0o600`` on POSIX). This raises
the bar against naive tampering; a same-user process that can read the
key file can still forge a signature, which is why keychain-derived
keys are recommended for high-assurance deployments (see the operator
guide).

Files written before signing existed are treated as *legacy unsigned*:
they still load (so upgrades don't lock operators out) but a signature
is written on the next save. Pass ``require_signature=True`` to refuse
unsigned files outright.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_ACL_VERSION = 1
_DEFAULT_PATH_RELATIVE = ".je_auto_control/usb_acl.json"
_VALID_DEFAULTS = frozenset({"allow", "deny"})
_VALID_DECISIONS = frozenset({"allow", "deny", "prompt"})
_SIG_SUFFIX = ".sig"
_KEY_SUFFIX = ".key"
_KEY_BYTES = 32


def default_acl_path() -> Path:
    return Path(os.path.expanduser("~")) / _DEFAULT_PATH_RELATIVE


@dataclass
class AclRule:
    """One per-device entry in the ACL."""

    vendor_id: str
    product_id: str
    serial: Optional[str] = None
    label: str = ""
    allow: bool = True
    prompt_on_open: bool = False

    def matches(self, *, vendor_id: str, product_id: str,
                serial: Optional[str]) -> bool:
        if self.vendor_id != vendor_id or self.product_id != product_id:
            return False
        if self.serial is None:
            return True
        return self.serial == serial

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict) -> "AclRule":
        return cls(
            vendor_id=str(payload["vendor_id"]),
            product_id=str(payload["product_id"]),
            serial=(None if payload.get("serial") is None
                    else str(payload["serial"])),
            label=str(payload.get("label", "")),
            allow=bool(payload.get("allow", True)),
            prompt_on_open=bool(payload.get("prompt_on_open", False)),
        )


@dataclass
class _AclState:
    default: str = "deny"
    rules: List[AclRule] = field(default_factory=list)


class UsbAcl:
    """Persistent per-device allow-list."""

    def __init__(self, *, path: Optional[Path] = None,
                 default_policy: str = "deny",
                 hmac_key: Optional[bytes] = None,
                 require_signature: bool = False) -> None:
        self._path = Path(path) if path is not None else default_acl_path()
        self._sig_path = self._path.with_name(self._path.name + _SIG_SUFFIX)
        self._key_path = self._path.with_name(self._path.name + _KEY_SUFFIX)
        self._explicit_key = bytes(hmac_key) if hmac_key is not None else None
        self._require_signature = bool(require_signature)
        self._integrity_ok = True
        self._lock = threading.Lock()
        if default_policy not in _VALID_DEFAULTS:
            raise ValueError(
                f"default_policy must be one of {_VALID_DEFAULTS}",
            )
        self._state = _AclState(default=default_policy)
        if self._path.exists():
            self._load()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def integrity_ok(self) -> bool:
        """False once a signature mismatch was seen on load."""
        return self._integrity_ok

    @property
    def default_policy(self) -> str:
        with self._lock:
            return self._state.default

    def list_rules(self) -> List[AclRule]:
        with self._lock:
            return list(self._state.rules)

    def add_rule(self, rule: AclRule, *, persist: bool = True) -> None:
        with self._lock:
            self._state.rules.append(rule)
        if persist:
            self._save()

    def remove_rule(self, *, vendor_id: str, product_id: str,
                    serial: Optional[str] = None,
                    persist: bool = True) -> bool:
        with self._lock:
            new_rules = [
                r for r in self._state.rules
                if not (r.vendor_id == vendor_id
                        and r.product_id == product_id
                        and r.serial == serial)
            ]
            removed = len(new_rules) != len(self._state.rules)
            self._state.rules = new_rules
        if removed and persist:
            self._save()
        return removed

    def set_default_policy(self, policy: str, *, persist: bool = True) -> None:
        if policy not in _VALID_DEFAULTS:
            raise ValueError(
                f"default_policy must be one of {_VALID_DEFAULTS}",
            )
        with self._lock:
            self._state.default = policy
        if persist:
            self._save()

    def decide(self, *, vendor_id: str, product_id: str,
               serial: Optional[str]) -> str:
        """Return ``"allow"`` / ``"deny"`` / ``"prompt"`` for one OPEN."""
        with self._lock:
            for rule in self._state.rules:
                if rule.matches(vendor_id=vendor_id,
                                product_id=product_id, serial=serial):
                    if rule.prompt_on_open:
                        return "prompt"
                    return "allow" if rule.allow else "deny"
            return self._state.default

    def verify_integrity(self) -> bool:
        """Re-check the on-disk signature; True if intact or no file."""
        try:
            raw = self._path.read_bytes()
        except OSError:
            return True
        return self._verify_signature(raw)

    # --- Integrity (HMAC) --------------------------------------------------

    def _resolve_key(self, *, create: bool) -> Optional[bytes]:
        """Return the HMAC key, optionally generating + persisting one."""
        if self._explicit_key is not None:
            return self._explicit_key
        try:
            if self._key_path.exists():
                return self._key_path.read_bytes()
            if not create:
                return None
            key = secrets.token_bytes(_KEY_BYTES)
            self._key_path.parent.mkdir(parents=True, exist_ok=True)
            self._key_path.write_bytes(key)
            if os.name == "posix":
                os.chmod(self._key_path, 0o600)
            return key
        except OSError as error:
            autocontrol_logger.warning(
                "usb acl key access %s failed: %r", self._key_path, error,
            )
            return None

    @staticmethod
    def _compute_sig(data: bytes, key: bytes) -> str:
        return hmac.new(key, data, hashlib.sha256).hexdigest()

    def _verify_signature(self, raw: bytes) -> bool:
        """True iff ``raw`` matches the sidecar signature (or is legacy)."""
        if not self._sig_path.exists():
            if self._require_signature:
                autocontrol_logger.warning(
                    "usb acl %s unsigned and require_signature set — deny",
                    self._path,
                )
                return False
            autocontrol_logger.info(
                "usb acl %s has no signature (legacy/unsigned)", self._path,
            )
            return True
        key = self._resolve_key(create=False)
        if key is None:
            autocontrol_logger.warning(
                "usb acl signature present but key unavailable for %s",
                self._path,
            )
            return False
        try:
            expected = self._sig_path.read_text(encoding="utf-8").strip()
        except OSError as error:
            autocontrol_logger.warning(
                "usb acl signature read %s failed: %r", self._sig_path, error,
            )
            return False
        return hmac.compare_digest(expected, self._compute_sig(raw, key))

    def _write_signature(self, data: bytes) -> None:
        key = self._resolve_key(create=True)
        if key is None:
            return
        try:
            self._sig_path.write_text(
                self._compute_sig(data, key), encoding="utf-8",
            )
            if os.name == "posix":
                os.chmod(self._sig_path, 0o600)
        except OSError as error:
            autocontrol_logger.warning(
                "usb acl signature write %s failed: %r", self._sig_path, error,
            )

    # --- Persistence -------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = self._path.read_bytes()
        except OSError as error:
            autocontrol_logger.warning(
                "usb acl load %s failed: %r", self._path, error,
            )
            return
        if not self._verify_signature(raw):
            self._integrity_ok = False
            autocontrol_logger.warning(
                "usb acl signature mismatch for %s — refusing to load "
                "(fail closed, default-deny)", self._path,
            )
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except ValueError as error:
            autocontrol_logger.warning(
                "usb acl parse %s failed: %r", self._path, error,
            )
            return
        try:
            version = int(payload.get("version", 0))
            if version != _ACL_VERSION:
                autocontrol_logger.warning(
                    "usb acl version %s unsupported (want %s); ignoring file",
                    version, _ACL_VERSION,
                )
                return
            default = str(payload.get("default", "deny"))
            if default not in _VALID_DEFAULTS:
                default = "deny"
            rules_payload = payload.get("rules", [])
            if not isinstance(rules_payload, list):
                rules_payload = []
            rules = [AclRule.from_dict(r) for r in rules_payload
                     if isinstance(r, dict)]
        except (KeyError, TypeError, ValueError) as error:
            autocontrol_logger.warning(
                "usb acl parse failed: %r — using default-deny", error,
            )
            return
        with self._lock:
            self._state = _AclState(default=default, rules=rules)

    def _save(self) -> None:
        with self._lock:
            payload = {
                "version": _ACL_VERSION,
                "default": self._state.default,
                "rules": [r.to_dict() for r in self._state.rules],
            }
        data = json.dumps(
            payload, indent=2, ensure_ascii=False,
        ).encode("utf-8")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_bytes(data)
            if os.name == "posix":
                os.chmod(self._path, 0o600)
        except OSError as error:
            autocontrol_logger.warning(
                "usb acl save %s failed: %r", self._path, error,
            )
            return
        # A freshly written file is, by definition, intact again.
        self._write_signature(data)
        self._integrity_ok = True


__all__ = [
    "AclRule", "UsbAcl", "default_acl_path",
]
