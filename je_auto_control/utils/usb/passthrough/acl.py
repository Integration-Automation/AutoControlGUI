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

File integrity (HMAC / keychain signing) is intentionally out of scope
for Phase 2d — see the design doc's "open question 8".
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_ACL_VERSION = 1
_DEFAULT_PATH_RELATIVE = ".je_auto_control/usb_acl.json"
_VALID_DEFAULTS = frozenset({"allow", "deny"})
_VALID_DECISIONS = frozenset({"allow", "deny", "prompt"})


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
                 default_policy: str = "deny") -> None:
        self._path = Path(path) if path is not None else default_acl_path()
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

    # --- Persistence -------------------------------------------------------

    def _load(self) -> None:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            autocontrol_logger.warning(
                "usb acl load %s failed: %r", self._path, error,
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
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            if os.name == "posix":
                os.chmod(self._path, 0o600)
        except OSError as error:
            autocontrol_logger.warning(
                "usb acl save %s failed: %r", self._path, error,
            )


__all__ = [
    "AclRule", "UsbAcl", "default_acl_path",
]
