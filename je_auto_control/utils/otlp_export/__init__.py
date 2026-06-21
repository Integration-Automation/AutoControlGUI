"""OTLP/JSON span export for AutoControl."""
from je_auto_control.utils.otlp_export.otlp_export import (
    attributes_to_otlp, spans_to_otlp, write_otlp,
)

__all__ = ["attributes_to_otlp", "spans_to_otlp", "write_otlp"]
