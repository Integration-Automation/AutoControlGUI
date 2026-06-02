"""Flaky-test quarantine — skip known-unstable cases in the suite runner.

Public surface::

    from je_auto_control import (
        QuarantineStore, default_quarantine_store,
        auto_quarantine_from_flakiness,
    )
"""
from je_auto_control.utils.quarantine.store import (
    QuarantineEntry,
    QuarantineStore,
    auto_quarantine_from_flakiness,
    default_quarantine_store,
    quarantined_names,
)


__all__ = [
    "QuarantineEntry",
    "QuarantineStore",
    "auto_quarantine_from_flakiness",
    "default_quarantine_store",
    "quarantined_names",
]
