"""Evaluation results as a comparison table: versions as rows, not raw JSON."""
import json

import numpy as np
import pytest

from je_auto_control.utils.cv2_utils.image_file import write_image
from je_auto_control.utils.self_healing import (
    COMPARISON_COLUMNS, HealingEvaluationError, comparison_rows,
    evaluate_healing_dataset,
)


def _noise(seed):
    return np.random.default_rng(seed).integers(0, 255, (20, 30), dtype=np.uint8)


@pytest.fixture
def dataset(tmp_path):
    old, new = _noise(1), _noise(2)
    frame = np.full((100, 160), 128, dtype=np.uint8)
    frame[30:50, 60:90] = new
    write_image(tmp_path / "old.png", old)
    write_image(tmp_path / "new.png", new)
    write_image(tmp_path / "frame.png", frame)
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps({
        "samples": [
            {"id": "old-look", "frame": "frame.png", "template": "old.png",
             "expected_box": [60, 30, 90, 50]},
            {"id": "new-look", "frame": "frame.png", "template": "new.png",
             "expected_box": [60, 30, 90, 50]},
            {"id": "absent", "frame": "frame.png", "template": "old.png", "expect_miss": True},
        ],
        "versions": {"strict": {"threshold": 0.99}, "model": {"strategy": "vlm",
                                                              "backend": "null"}},
    }), encoding="utf-8")
    return path


def test_rows_hold_counts_with_their_rates_and_dashes_for_what_nobody_reported(dataset):
    payload = evaluate_healing_dataset(dataset)
    rows = comparison_rows(payload)
    assert [row["version"] for row in rows] == ["strict", "model"]
    strict, model = rows
    assert strict["baseline"] is True
    assert model["baseline"] is False
    assert set(strict) == set(COMPARISON_COLUMNS) | {"baseline"}
    assert strict["located"] == "1/3 (33.3%)"
    assert strict["accuracy"] == "2/3 (66.7%)"
    assert strict["false_positive"] == "0/3 (0.0%)"
    assert strict["recovery"] == "0/1 (0.0%)"
    assert (strict["model_calls"], strict["tokens"], strict["cost"]) == ("0", "-", "-")
    assert float(strict["p50_ms"]) >= 0
    assert float(strict["p95_ms"]) >= float(strict["p50_ms"])
    assert model["located"] == "0/3 (0.0%)"


def test_the_baseline_comes_first_whatever_the_order_and_rates_over_nothing_say_so():
    ratio = {"numerator": 0, "denominator": 0, "value": None}
    report = {"hit_rate": ratio, "accuracy": ratio, "false_positive_rate": ratio,
              "recovery_rate": ratio, "p50_ms": None, "p95_ms": None, "model_calls": 4,
              "input_tokens": 900, "output_tokens": None, "cost": 0.0125}
    rows = comparison_rows({"baseline": "b", "versions": {"a": report, "b": report}})
    assert [row["version"] for row in rows] == ["b", "a"]
    assert rows[0]["accuracy"] == "0/0 (n/a)"
    assert rows[0]["p50_ms"] == "-"
    assert (rows[0]["model_calls"], rows[0]["tokens"], rows[0]["cost"]) == (
        "4", "900 / -", "0.0125")
    with pytest.raises(HealingEvaluationError):
        comparison_rows({"results": []})


def test_every_catalogue_has_the_column_headings():
    from je_auto_control.gui.language_wrapper import (
        english, japanese, simplified_chinese, traditional_chinese,
    )
    wanted = {f"self_heal_cmp_{name}" for name in COMPARISON_COLUMNS} | {
        "self_heal_cmp_baseline"}
    for module in (english, japanese, simplified_chinese, traditional_chinese):
        catalogue = next(value for value in vars(module).values()
                         if isinstance(value, dict) and "self_heal_refresh" in value)
        assert not wanted - set(catalogue), module.__name__
        assert "{name}" in catalogue["self_heal_cmp_baseline"]


def test_the_tab_shows_the_table(dataset):
    pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from je_auto_control.gui import self_healing_tab
    tab = self_healing_tab.SelfHealingTab()
    try:
        table = tab._compare_table
        assert table.columnCount() == len(COMPARISON_COLUMNS)
        assert table.rowCount() == 0
        headers = [table.horizontalHeaderItem(col).text() for col in range(table.columnCount())]
        assert headers == [self_healing_tab._t(f"self_heal_cmp_{name}")
                           for name in COMPARISON_COLUMNS]
        assert not any(header.startswith("self_heal_") for header in headers)
        tab._dataset_input.setText(str(dataset))
        tab._on_evaluate()
        assert table.rowCount() == 2
        cells = [table.item(0, col).text() for col in range(table.columnCount())]
        assert cells[0] == self_healing_tab._t("self_heal_cmp_baseline").replace(
            "{name}", "strict")
        assert cells[2] == "2/3 (66.7%)"
        assert table.item(1, 0).text() == "model"
        # The full report is still there for the failing samples.
        assert json.loads(tab._report_view.toPlainText())["baseline"] == "strict"
    finally:
        tab.deleteLater()
        app.processEvents()
