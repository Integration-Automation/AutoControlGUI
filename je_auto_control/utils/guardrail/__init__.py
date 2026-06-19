"""Heuristic prompt-injection guardrail for screen / OCR text."""
from je_auto_control.utils.guardrail.guardrail import (
    GuardrailFinding, assess_text, redact_text, scan_text,
)

__all__ = ["GuardrailFinding", "assess_text", "redact_text", "scan_text"]
