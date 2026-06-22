"""Find and mask personally-identifiable information in arbitrary strings.

The image-redaction module blurs PII in screenshots, but text scraped from a UI,
OCR, the clipboard, an LLM prompt/response, or a log line had no string-level
equivalent — so PII could leak into action records, audit logs, or a model call.
This detects emails, phone numbers, SSNs, credit-card numbers, IPv4 addresses,
and IBANs over plain text and redacts them with a chosen strategy.

Patterns are deliberately simple (no nested quantifiers → no catastrophic
backtracking). Pure standard library (``re`` + ``hashlib``); imports no
``PySide6``.
"""
import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

PII_KINDS = ("email", "ipv4", "ssn", "credit_card", "iban", "phone")

_PATTERNS: Dict[str, "re.Pattern[str]"] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(
        r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,4}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b"),
    "phone": re.compile(r"\+?\d[\d().\- ]{6,12}\d"),
}


@dataclass(frozen=True)
class PIIFinding:
    """One detected PII span."""

    kind: str
    value: str
    start: int
    end: int


def detect_pii(text: str, *,
               kinds: Optional[Sequence[str]] = None) -> List[PIIFinding]:
    """Return non-overlapping PII findings in ``text``, sorted by position.

    ``kinds`` restricts which detectors run (defaults to all). When spans
    overlap, the earlier — then longer — match wins (so a credit-card number is
    not also reported as a phone number).
    """
    wanted = list(kinds) if kinds else list(PII_KINDS)
    candidates: List[PIIFinding] = []
    for kind in wanted:
        pattern = _PATTERNS.get(kind)
        if pattern is None:
            continue
        candidates.extend(
            PIIFinding(kind, m.group(0), m.start(), m.end())
            for m in pattern.finditer(text))
    candidates.sort(key=lambda f: (f.start, -(f.end - f.start)))
    kept: List[PIIFinding] = []
    last_end = -1
    for finding in candidates:
        if finding.start >= last_end:
            kept.append(finding)
            last_end = finding.end
    return kept


def _mask(value: str, kind: str, mode: str, mask_char: str) -> str:
    if mode == "label":
        return f"[{kind}]"
    if mode == "partial":
        tail = value[-4:]
        return mask_char * max(0, len(value) - 4) + tail
    if mode == "hash":
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
        return f"[{kind}:{digest}]"
    return mask_char * len(value)


def redact_pii_text(text: str, *, kinds: Optional[Sequence[str]] = None,
                    mode: str = "label", mask_char: str = "*") -> str:
    """Return ``text`` with PII replaced.

    ``mode``: ``label`` (``[email]``), ``mask`` (``****``), ``partial`` (keep
    last 4), or ``hash`` (``[email:1a2b3c4d]``).
    """
    findings = detect_pii(text, kinds=kinds)
    result = text
    for finding in reversed(findings):     # right-to-left keeps offsets valid
        replacement = _mask(finding.value, finding.kind, mode, mask_char)
        result = result[:finding.start] + replacement + result[finding.end:]
    return result
