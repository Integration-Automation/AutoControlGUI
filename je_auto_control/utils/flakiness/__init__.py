"""Flaky-test detection — analytics over the run-history store.

Public surface::

    from je_auto_control import (
        analyze_flakiness, FlakinessReport, FlakyEntry,
    )
"""
from je_auto_control.utils.flakiness.flakiness import (
    FlakinessReport,
    FlakyEntry,
    analyze_flakiness,
)


__all__ = ["FlakinessReport", "FlakyEntry", "analyze_flakiness"]
