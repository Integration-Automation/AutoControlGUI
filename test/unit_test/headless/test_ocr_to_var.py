"""Tests for AC_ocr_to_var (OCR a region into a flow variable)."""
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.executor.flow_control import exec_ocr_to_var


class _Match:
    def __init__(self, text):
        self.text = text


def test_ocr_to_var_binds_recognised_text(monkeypatch):
    monkeypatch.setattr(
        "je_auto_control.utils.ocr.ocr_engine.read_text_in_region",
        lambda region=None, lang="eng", min_confidence=60.0: [
            _Match("Order"), _Match("12345")],
    )
    executor = Executor()
    result = exec_ocr_to_var(
        executor, {"var": "order_id", "region": [0, 0, 200, 40]},
    )
    assert result["text"] == "Order 12345"
    assert executor.variables.get_value("order_id") == "Order 12345"


def test_ocr_to_var_uses_default_var_name(monkeypatch):
    monkeypatch.setattr(
        "je_auto_control.utils.ocr.ocr_engine.read_text_in_region",
        lambda region=None, lang="eng", min_confidence=60.0: [_Match("hi")],
    )
    executor = Executor()
    exec_ocr_to_var(executor, {})
    assert executor.variables.get_value("ocr_text") == "hi"


def test_ocr_to_var_parses_json_region(monkeypatch):
    captured = {}

    def fake_read(region=None, lang="eng", min_confidence=60.0):
        captured["region"] = region
        return []

    monkeypatch.setattr(
        "je_auto_control.utils.ocr.ocr_engine.read_text_in_region", fake_read,
    )
    exec_ocr_to_var(Executor(), {"region": "[1, 2, 3, 4]"})
    assert captured["region"] == [1, 2, 3, 4]
