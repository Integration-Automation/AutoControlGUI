"""Headless tests for table headers + cell addressing (fake backend seam)."""
import je_auto_control as ac
from je_auto_control.utils.accessibility.backends import base as backend_base
from je_auto_control.utils.table_pattern import (
    cell_by_header, table_cell, table_headers,
)

_HEADERS = {"columns": ["Order", "Status", "Total"], "rows": ["r0", "r1"]}
_GRID = {
    (0, 0): "Order 5", (0, 1): "Shipped", (0, 2): "$10",
    (1, 0): "Order 6", (1, 1): "Pending", (1, 2): "$20",
}


class _FakeBackend(backend_base.AccessibilityBackend):
    name = "fake"
    available = True

    def __init__(self, headers=None, grid=None):
        self._headers = headers
        self._grid = grid or {}

    def get_table_headers(self, name=None, role=None, app_name=None,
                          automation_id=None):
        return self._headers

    def get_grid_cell(self, row=0, column=0, name=None, role=None,
                      app_name=None, automation_id=None):
        if (row, column) not in self._grid:
            return None
        return {"value": self._grid[(row, column)], "row": row, "column": column,
                "row_span": 1, "column_span": 1}


def _inject(monkeypatch, backend):
    import je_auto_control.utils.accessibility.backends as backends
    monkeypatch.setattr(backends, "_cached_backend", backend, raising=False)


def test_table_headers(monkeypatch):
    _inject(monkeypatch, _FakeBackend(dict(_HEADERS)))
    assert table_headers(name="Orders") == _HEADERS


def test_table_cell_by_index(monkeypatch):
    _inject(monkeypatch, _FakeBackend(grid=dict(_GRID)))
    cell = table_cell(0, 1, name="Orders")
    assert cell["value"] == "Shipped"
    assert cell["row"] == 0 and cell["column"] == 1
    assert table_cell(9, 9, name="Orders") is None


def test_cell_by_header_resolves_column(monkeypatch):
    _inject(monkeypatch, _FakeBackend(dict(_HEADERS), dict(_GRID)))
    # row 0, "Status" column → resolves to column index 1 → "Shipped"
    assert cell_by_header(0, "Status", name="Orders") == "Shipped"
    assert cell_by_header(1, "Order", name="Orders") == "Order 6"


def test_cell_by_header_unknown_column(monkeypatch):
    _inject(monkeypatch, _FakeBackend(dict(_HEADERS), dict(_GRID)))
    assert cell_by_header(0, "Nonexistent", name="Orders") is None


def test_cell_by_header_no_headers(monkeypatch):
    _inject(monkeypatch, _FakeBackend(None, dict(_GRID)))
    assert cell_by_header(0, "Status", name="Orders") is None


def test_unsupported_backend_raises(monkeypatch):
    from je_auto_control.utils.accessibility.element import (
        AccessibilityNotAvailableError)
    _inject(monkeypatch, backend_base.AccessibilityBackend())
    try:
        table_headers(name="x")
        raised = False
    except AccessibilityNotAvailableError:
        raised = True
    assert raised is True


# --- wiring ---------------------------------------------------------------

def test_executor_adapters(monkeypatch):
    _inject(monkeypatch, _FakeBackend(dict(_HEADERS), dict(_GRID)))
    from je_auto_control.utils.executor.action_executor import (
        _cell_by_header, _table_cell, _table_headers)
    assert _table_headers(name="Orders")["headers"]["columns"][1] == "Status"
    assert _table_cell(0, 2, name="Orders")["cell"]["value"] == "$10"
    out = _cell_by_header(0, "Status", name="Orders")
    assert out["found"] is True and out["value"] == "Shipped"


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_table_headers", "AC_table_cell", "AC_cell_by_header"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_table_headers", "ac_table_cell", "ac_cell_by_header"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_table_headers", "AC_table_cell", "AC_cell_by_header"} <= specs


def test_facade_exports():
    for name in ("table_headers", "table_cell", "cell_by_header"):
        assert hasattr(ac, name) and name in ac.__all__
