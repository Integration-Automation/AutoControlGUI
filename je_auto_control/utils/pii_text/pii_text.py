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

from je_auto_control.utils.checksum.checksum import mod97_10_validate

PII_KINDS = ("email", "ipv4", "ssn", "credit_card", "iban", "phone")

_PATTERNS: Dict[str, "re.Pattern[str]"] = {
    # Bounded, and anchored to a boundary: the unbounded local part rescanned
    # to the end from every position (quadratic on 20 KB of letters).
    "email": re.compile(
        r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,24}"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # 13-19 digits in any grouping (Amex is 4-6-5), confirmed by Luhn below.
    "credit_card": re.compile(r"\b\d(?:[ -]?\d){12,18}\b"),
    # ISO 13616: compact, or the print format in groups of four
    # ("DE89 3704 0044 0532 0130 00"); confirmed by mod-97 below.
    "iban": re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b"),
    # Up to 20 characters: "+1 (555) 123-4567" and "+44 20 7946 0958" were
    # cut at 15 and their last digits left visible.
    "phone": re.compile(r"(?<![\w+])\+?\(?\d[\d().\- ]{6,18}\d(?!\w)"),
}


def luhn_valid(number: str) -> bool:
    """Whether the digits of ``number`` pass the Luhn checksum card numbers carry."""
    digits = [int(char) for char in number if char.isdigit()]
    if len(digits) < 13:
        return False
    total = 0
    for position, digit in enumerate(reversed(digits)):
        if position % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _iban_valid(value: str) -> bool:
    """ISO 13616 mod-97: the rearranged IBAN, letters as 10..35, leaves 1."""
    compact = value.replace(" ", "").upper()
    if not 15 <= len(compact) <= 34:
        return False
    rearranged = compact[4:] + compact[:4]
    return mod97_10_validate("".join(str(int(char, 36)) for char in rearranged))


def _confirmed(kind: str, value: str) -> bool:
    """Checksum the kinds that carry one (Luhn for cards, mod-97 for IBANs)."""
    if kind == "credit_card":
        return luhn_valid(value)
    if kind == "iban":
        return _iban_valid(value)
    return True


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
            for m in pattern.finditer(text)
            if _confirmed(kind, m.group(0)))
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
