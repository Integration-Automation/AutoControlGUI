"""Table headers and cell addressing for native grids (UIA TablePattern).

``read_control_table`` (GridPattern) dumps a flat 2-D list of cell names with **no
header labels and no way to address a single cell by (header, row)** — so you can
dump a grid but not actually *test* one. ``table_pattern`` adds the missing half:

* :func:`table_headers` — the row / column header labels (TablePattern),
* :func:`table_cell` — the cell at ``(row, column)`` with its span (GridItemPattern),
* :func:`cell_by_header` — read the cell at ``(row, "Column Header")`` — so you can
  assert "the Status column of row 5 says Shipped" without guessing indices.

Each is a thin dispatch onto the injectable ``accessibility.backends.get_backend()``
seam, so the headless core is unit-testable by injecting a fake backend; the real
UIA calls live in the Windows backend. Imports no ``PySide6``.
"""
from typing import Any, Dict, Optional


def _backend():
    from je_auto_control.utils.accessibility.backends import get_backend
    return get_backend()


def table_headers(name: Optional[str] = None, role: Optional[str] = None,
                  app_name: Optional[str] = None,
                  automation_id: Optional[str] = None,
                  ) -> Optional[Dict[str, Any]]:
    """Return a table's header labels as ``{columns: [...], rows: [...]}``, or None."""
    return _backend().get_table_headers(name=name, role=role, app_name=app_name,
                                        automation_id=automation_id)


def table_cell(row: int, column: int, name: Optional[str] = None,
               role: Optional[str] = None, app_name: Optional[str] = None,
               automation_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Return the cell at ``(row, column)`` as ``{value, row, column, row_span,
    column_span}``, or None if the grid / cell isn't found."""
    return _backend().get_grid_cell(int(row), int(column), name=name, role=role,
                                    app_name=app_name, automation_id=automation_id)


def cell_by_header(row: int, column_header: str, name: Optional[str] = None,
                   role: Optional[str] = None, app_name: Optional[str] = None,
                   automation_id: Optional[str] = None) -> Optional[str]:
    """Return the value of the cell at ``row`` in the column named ``column_header``.

    Resolves the column index from the table's headers, then reads the cell —
    ``None`` if the header or cell isn't found.
    """
    headers = table_headers(name=name, role=role, app_name=app_name,
                            automation_id=automation_id)
    if not headers:
        return None
    columns = headers.get("columns", [])
    if column_header not in columns:
        return None
    cell = table_cell(int(row), columns.index(column_header), name=name,
                      role=role, app_name=app_name, automation_id=automation_id)
    return cell.get("value") if cell else None
