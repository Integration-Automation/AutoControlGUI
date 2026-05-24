"""Cluster raw OCR matches into rows / tables / form-field pairs.

Builds on top of the existing :func:`read_text_in_region` output. Pure
Python — same input, structured output. The detection heuristics are
intentionally simple so the result is predictable and easy to debug:

* **Rows** group matches whose vertical centres lie within
  ``row_tolerance_px`` (default: half the median glyph height).
* **Tables** are sets of consecutive rows whose cell count and
  cell-left-x positions agree within ``column_tolerance_px``.
* **Fields** pair a label match (text ending in ``:``) with the
  nearest match to its right (or below, when nothing to the right).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any, Dict, List, Optional, Sequence, Tuple

from je_auto_control.utils.ocr.ocr_engine import TextMatch


_DEFAULT_ROW_TOLERANCE = 0.5
_DEFAULT_COLUMN_TOLERANCE_PX = 12.0
_DEFAULT_MIN_TABLE_ROWS = 2
_DEFAULT_MIN_TABLE_COLUMNS = 2


@dataclass(frozen=True)
class OCRRow:
    """One horizontal row of OCR cells (sorted by x)."""

    cells: Tuple[TextMatch, ...]
    bbox: Tuple[int, int, int, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bbox": list(self.bbox),
            "cells": [_match_to_dict(cell) for cell in self.cells],
        }


@dataclass(frozen=True)
class OCRTable:
    """A consecutive set of OCR rows sharing column alignment."""

    rows: Tuple[OCRRow, ...]
    bbox: Tuple[int, int, int, int]
    column_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bbox": list(self.bbox),
            "column_count": int(self.column_count),
            "rows": [row.to_dict() for row in self.rows],
        }


@dataclass(frozen=True)
class OCRField:
    """A label : value pair detected by spatial adjacency."""

    label: str
    value: str
    label_match: TextMatch
    value_match: TextMatch

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label, "value": self.value,
            "label_match": _match_to_dict(self.label_match),
            "value_match": _match_to_dict(self.value_match),
        }


@dataclass(frozen=True)
class StructuredOCR:
    """All four views of one OCR pass."""

    matches: Tuple[TextMatch, ...] = field(default_factory=tuple)
    rows: Tuple[OCRRow, ...] = field(default_factory=tuple)
    tables: Tuple[OCRTable, ...] = field(default_factory=tuple)
    fields: Tuple[OCRField, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matches": [_match_to_dict(m) for m in self.matches],
            "rows": [row.to_dict() for row in self.rows],
            "tables": [table.to_dict() for table in self.tables],
            "fields": [field_.to_dict() for field_ in self.fields],
        }


def cluster_matches(matches: Sequence[TextMatch],
                    *,
                    row_tolerance_px: Optional[float] = None,
                    column_tolerance_px: float = _DEFAULT_COLUMN_TOLERANCE_PX,
                    min_table_rows: int = _DEFAULT_MIN_TABLE_ROWS,
                    min_table_columns: int = _DEFAULT_MIN_TABLE_COLUMNS,
                    ) -> StructuredOCR:
    """Group raw OCR matches into rows, tables, and key→value fields."""
    cleaned = [m for m in matches if isinstance(m, TextMatch)]
    if not cleaned:
        return StructuredOCR()
    tolerance = _resolve_row_tolerance(cleaned, row_tolerance_px)
    rows = _build_rows(cleaned, tolerance)
    tables = _detect_tables(
        rows,
        column_tolerance=float(column_tolerance_px),
        min_rows=int(min_table_rows),
        min_columns=int(min_table_columns),
    )
    fields = _detect_fields(rows)
    return StructuredOCR(
        matches=tuple(cleaned),
        rows=tuple(rows),
        tables=tuple(tables),
        fields=tuple(fields),
    )


def read_structure(region: Optional[Sequence[int]] = None,
                   *, lang: str = "eng",
                   min_confidence: float = 60.0,
                   backend: Optional[Any] = None,
                   row_tolerance_px: Optional[float] = None,
                   column_tolerance_px: float = _DEFAULT_COLUMN_TOLERANCE_PX,
                   min_table_rows: int = _DEFAULT_MIN_TABLE_ROWS,
                   min_table_columns: int = _DEFAULT_MIN_TABLE_COLUMNS,
                   ) -> StructuredOCR:
    """Capture ``region`` (or whole screen) and return a :class:`StructuredOCR`."""
    from je_auto_control.utils.ocr.ocr_engine import read_text_in_region
    matches = read_text_in_region(
        region=region, lang=lang,
        min_confidence=float(min_confidence), backend=backend,
    )
    return cluster_matches(
        matches,
        row_tolerance_px=row_tolerance_px,
        column_tolerance_px=column_tolerance_px,
        min_table_rows=min_table_rows,
        min_table_columns=min_table_columns,
    )


# --- helpers ----------------------------------------------------

def _resolve_row_tolerance(matches: Sequence[TextMatch],
                            override: Optional[float]) -> float:
    if override is not None:
        return float(override)
    heights = [m.height for m in matches if m.height > 0]
    median_height = median(heights) if heights else 12.0
    return median_height * _DEFAULT_ROW_TOLERANCE


def _build_rows(matches: Sequence[TextMatch],
                tolerance: float) -> List[OCRRow]:
    sorted_by_y = sorted(matches, key=lambda m: m.y + m.height / 2)
    rows: List[List[TextMatch]] = []
    for match in sorted_by_y:
        center_y = match.y + match.height / 2
        placed = False
        for bucket in rows:
            bucket_center = bucket[0].y + bucket[0].height / 2
            if abs(center_y - bucket_center) <= tolerance:
                bucket.append(match)
                placed = True
                break
        if not placed:
            rows.append([match])
    return [_finalise_row(bucket) for bucket in rows]


def _finalise_row(cells: List[TextMatch]) -> OCRRow:
    ordered = sorted(cells, key=lambda m: m.x)
    x1 = min(c.x for c in ordered)
    y1 = min(c.y for c in ordered)
    x2 = max(c.x + c.width for c in ordered)
    y2 = max(c.y + c.height for c in ordered)
    return OCRRow(cells=tuple(ordered), bbox=(x1, y1, x2, y2))


def _detect_tables(rows: List[OCRRow], *,
                    column_tolerance: float,
                    min_rows: int,
                    min_columns: int) -> List[OCRTable]:
    if len(rows) < min_rows:
        return []
    tables: List[OCRTable] = []
    current: List[OCRRow] = []
    current_columns: List[float] = []
    for row in rows:
        starts = [cell.x for cell in row.cells]
        if len(starts) < min_columns:
            tables.extend(_flush_table(current, min_rows))
            current, current_columns = [], []
            continue
        if not current_columns:
            current = [row]
            current_columns = list(starts)
            continue
        if _columns_match(current_columns, starts, column_tolerance):
            current.append(row)
        else:
            tables.extend(_flush_table(current, min_rows))
            current = [row]
            current_columns = list(starts)
    tables.extend(_flush_table(current, min_rows))
    return tables


def _flush_table(rows: List[OCRRow], min_rows: int) -> List[OCRTable]:
    if len(rows) < min_rows:
        return []
    x1 = min(row.bbox[0] for row in rows)
    y1 = min(row.bbox[1] for row in rows)
    x2 = max(row.bbox[2] for row in rows)
    y2 = max(row.bbox[3] for row in rows)
    return [OCRTable(
        rows=tuple(rows), bbox=(x1, y1, x2, y2),
        column_count=len(rows[0].cells),
    )]


def _columns_match(reference: Sequence[float],
                    candidate: Sequence[int],
                    tolerance: float) -> bool:
    if len(reference) != len(candidate):
        return False
    return all(abs(r - c) <= tolerance for r, c in zip(reference, candidate))


def _detect_fields(rows: List[OCRRow]) -> List[OCRField]:
    fields: List[OCRField] = []
    for row_index, row in enumerate(rows):
        for cell_index, cell in enumerate(row.cells):
            cleaned = cell.text.strip()
            if not cleaned.endswith(":"):
                continue
            value = _find_field_value(rows, row_index, cell_index)
            if value is None:
                continue
            fields.append(OCRField(
                label=cleaned.rstrip(":").strip(),
                value=value.text.strip(),
                label_match=cell, value_match=value,
            ))
    return fields


def _find_field_value(rows: List[OCRRow], row_index: int,
                       cell_index: int) -> Optional[TextMatch]:
    """First try the next cell on the same row; otherwise the next row's first cell."""
    row = rows[row_index]
    if cell_index + 1 < len(row.cells):
        return row.cells[cell_index + 1]
    if row_index + 1 < len(rows) and rows[row_index + 1].cells:
        return rows[row_index + 1].cells[0]
    return None


def _match_to_dict(match: TextMatch) -> Dict[str, Any]:
    return {
        "text": match.text,
        "x": int(match.x), "y": int(match.y),
        "width": int(match.width), "height": int(match.height),
        "confidence": float(match.confidence),
    }


__all__ = [
    "OCRField", "OCRRow", "OCRTable", "StructuredOCR",
    "cluster_matches", "read_structure",
]
