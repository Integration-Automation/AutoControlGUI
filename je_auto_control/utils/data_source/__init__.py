"""Data-driven execution — load rows from CSV / JSON / SQLite / Excel.

Public surface::

    from je_auto_control import load_rows, data_source_kinds
"""
from je_auto_control.utils.data_source.data_source import (
    load_rows,
    supported_kinds as data_source_kinds,
)


__all__ = ["load_rows", "data_source_kinds"]
