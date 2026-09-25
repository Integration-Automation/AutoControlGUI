"""Test-infrastructure and statistics helpers at the edges the audit found.

Re-merged shard reports, time-series edges at Unix-time magnitudes, a regex
text assertion's ignore_case, the screen-stable clock, the documented cost
summary call and current list prices, huge integers in row validation, and
the Student t quantile for tiny alpha.
"""
import math

import pytest

from je_auto_control.utils.cost_telemetry import estimate_llm_usd, summarise_llm_costs
from je_auto_control.utils.data_quality.data_quality import validate_rows
from je_auto_control.utils.stats.stats import _t_critical
from je_auto_control.utils.test_shard.test_shard import merge_results
from je_auto_control.utils.timeseries.timeseries import _bucket_index, ts_downsample


def _report(passed, errored):
    return {"total": passed + errored, "passed": passed, "failed": 0, "skipped": 0,
            "errored": errored,
            "cases": [{"name": f"c{i}"} for i in range(passed + errored)]}


def test_merging_merged_reports_does_not_double_count():
    first = merge_results([_report(2, 0), _report(0, 1)])
    assert (first["total"], first["errors"], len(first["results"])) == (3, 1, 3)
    top = merge_results([first, merge_results([_report(1, 0)])])
    assert (top["total"], top["errors"], len(top["results"])) == (4, 1, 4)
    assert merge_results([first])["errors"] == 1


def test_bucket_edges_hold_at_unix_time():
    base = 1_700_000_000
    assert _bucket_index(base + 0.3, 0.1) - base * 10 == 3
    wrong = sum(1 for i in range(1000)
                if _bucket_index(base + i / 1000, 0.001) - base * 1000 != i)
    assert wrong == 0
    points = ts_downsample([(base + 0.3, 1.0), (base + 0.35, 2.0)], 0.1, "first")
    assert len(points) == 1


def test_a_regex_text_assertion_ignores_case_by_default(monkeypatch):
    import je_auto_control.utils.ocr.ocr_engine as ocr
    from je_auto_control.utils.assertion.assertions import assert_text
    seen = []

    def fake_find(pattern, lang="eng", region=None, min_confidence=60.0, flags=0):
        seen.append(flags)
        return ["hit"] if flags else []

    monkeypatch.setattr(ocr, "find_text_regex", fake_find)
    monkeypatch.setattr(ocr, "read_text_in_region", lambda **kwargs: [], raising=False)
    assert assert_text("saved", regex=True, raise_on_fail=False).passed
    assert not assert_text("saved", regex=True, ignore_case=False, raise_on_fail=False).passed


def test_the_stable_clock_starts_at_the_first_matching_frame():
    from je_auto_control.utils.smart_waits.waits import Frame, wait_until_screen_stable
    frame = Frame(width=4, height=4, pixels=bytes(48))
    outcome = wait_until_screen_stable(timeout_s=0.5, poll_interval_s=0.2,
                                       stable_for_s=0.4, sampler=lambda region: frame)
    assert outcome.succeeded


def test_the_documented_cost_summary_call_works_and_prices_are_current():
    summary = summarise_llm_costs()
    assert summary is not None
    assert estimate_llm_usd("claude-opus-4-7", 1_000_000, 1_000_000) == 30.0
    assert estimate_llm_usd("claude-haiku-4-5", 1_000_000, 1_000_000) == 6.0
    assert estimate_llm_usd("claude-haiku-4-5-20251001", 1_000_000, 1_000_000) == 6.0
    assert estimate_llm_usd("anthropic.claude-opus-5", 1_000_000, 0) == 5.0
    assert estimate_llm_usd("claude-opus-5-5", 0, 1_000_000) == 20.0
    assert estimate_llm_usd("claude-3-5-haiku-20241022", 1_000_000, 1_000_000) == 4.8


def test_a_huge_integer_is_reported_not_raised():
    report = validate_rows([{"n": 10 ** 400}], {"n": {"type": "int", "max": 5}})
    assert "above max 5" in str(report)


@pytest.mark.parametrize("alpha, expected", [(0.0005, 1273.239), (0.0001, 6366.198)])
def test_the_t_quantile_is_not_capped(alpha, expected):
    # df = 1 is the Cauchy distribution: the two-sided quantile is cot(pi*alpha/2).
    assert _t_critical(alpha, 1.0) == pytest.approx(expected, rel=1e-3)
    assert _t_critical(alpha, 1.0) == pytest.approx(1 / math.tan(math.pi * alpha / 2), rel=1e-3)
