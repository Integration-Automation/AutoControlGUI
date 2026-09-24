"""Regression tests for the observability and report-output defects of the 2026-09-23 audit.

``to_otel`` claimed OTLP but had no ids, no timestamps and untyped
attributes. Labelled Prometheus metrics rendered a bogus unlabelled series,
accepted partial label sets and non-ASCII names, and HELP text was not
escaped. SBOM purls were not normalised, SARIF passed any level through,
put lint issues one line early and wrote OS paths as URIs. PEP 440 / SemVer
pre-releases sorted after their release in the vulnerability scan; W3C
multi-tenant tracestate keys were dropped. Step videos counted frames they
never wrote and drew on the caller's array; a zero-variance t-test and
negative token counts gave wrong numbers.
"""
import pytest

from je_auto_control.utils.agent_trace.agent_trace import AgentTrace
from je_auto_control.utils.cost_telemetry.store import CostStore
from je_auto_control.utils.observability.metrics import Counter, Gauge, Histogram
from je_auto_control.utils.sarif.sarif import from_lint_issues, make_finding, to_sarif
from je_auto_control.utils.sbom.sbom import _purl
from je_auto_control.utils.stats.stats import welch_t_test
from je_auto_control.utils.trace_context.trace_context import parse_tracestate
from je_auto_control.utils.vuln_scan.vuln_scan import is_affected


def test_to_otel_emits_otlp_spans():
    trace = AgentTrace()
    trace.record("chat", model="m", system="openai", input_tokens=3, duration_s=0.25)
    span = trace.to_otel()[0]
    assert len(span["traceId"]) == 32 and len(span["spanId"]) == 16
    assert int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"]) == 250_000_000
    assert (span["kind"], span["status"]["code"]) == (3, 1)
    assert {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "3"}} in span["attributes"]
    assert {"key": "gen_ai.provider.name", "value": {"stringValue": "openai"}} in span["attributes"]


def test_a_labelled_counter_has_no_unlabelled_series():
    counter = Counter("x_total", "h", label_names=("action",))
    counter.inc(labels={"action": "a"})
    samples = [line for line in counter.render().splitlines() if not line.startswith("#")]
    assert samples == ['x_total{action="a"} 1']


def test_a_partial_label_set_is_refused():
    counter = Counter("y_total", "h", label_names=("action", "outcome"))
    with pytest.raises(ValueError, match="missing"):
        counter.inc(labels={"action": "a"})


@pytest.mark.parametrize("name", ["m\u00e9trique", "x\u00b2"])
def test_non_ascii_metric_names_are_refused(name):
    with pytest.raises(ValueError):
        Counter(name, "h")


def test_colons_are_valid_in_metric_names():
    assert Counter("ns:requests_total", "h").name == "ns:requests_total"


def test_le_is_reserved_on_histograms():
    with pytest.raises(ValueError):
        Histogram("h_seconds", "h", label_names=("le",))


def test_help_text_is_escaped():
    first_line = Gauge("z", "line1\nline2").render().splitlines()[0]
    assert first_line == "# HELP z line1\\nline2"


@pytest.mark.parametrize("name, version, purl", [
    ("PySide6_Essentials", "6.7.0", "pkg:pypi/pyside6-essentials@6.7.0"),
    ("torch", "2.1.0+cu118", "pkg:pypi/torch@2.1.0%2Bcu118"),
])
def test_purls_are_normalised(name, version, purl):
    assert _purl(name, version) == purl


def test_sarif_levels_are_normalised():
    doc = to_sarif([make_finding("R1", "m", level="high"), {"rule_id": 101, "level": "critical",
                                                             "message": "x"}])
    results = doc["runs"][0]["results"]
    assert [r["level"] for r in results] == ["error", "error"]
    assert results[1]["ruleId"] == "101"


def test_sarif_lint_lines_are_one_based():
    findings = from_lint_issues([{"index": 0, "severity": "error", "code": "E1", "message": "m"}],
                                file="flow.json")
    region = to_sarif(findings)["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
    assert region == {"startLine": 1}


def test_sarif_uris_are_uris():
    location = to_sarif([make_finding("R", "m", file="C:\\my dir\\flow file.json")])
    uri = location["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == "file:///C:/my%20dir/flow%20file.json"


def test_sarif_refuses_a_line_below_one():
    result = to_sarif([make_finding("R", "m", file="a.json", line=-2)])["runs"][0]["results"][0]
    assert "region" not in result["locations"][0]["physicalLocation"]


_RANGE = {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.0.0"}]}


@pytest.mark.parametrize("version, affected", [
    ("2.0.0rc1", True), ("2.0.0.dev1", True), ("2.0", False), ("2.0.0.post1", False),
])
def test_pep440_versions_order_around_the_release(version, affected):
    assert is_affected(version, _RANGE) is affected


def test_semver_prerelease_identifiers_compare_numerically():
    semver_range = {"type": "SEMVER", "events": [{"introduced": "0"}, {"fixed": "1.0.0-alpha.10"}]}
    assert is_affected("1.0.0-alpha.2", semver_range) is True


def test_multi_tenant_tracestate_keys_are_kept():
    state = parse_tracestate("fw529a3039@dt=00f067aa0ba902b7,congo=t61rcWkgMzE")
    assert [key for key, _ in state] == ["fw529a3039@dt", "congo"]


def test_a_duplicated_tracestate_key_invalidates_the_header():
    assert parse_tracestate("a=1,a=2") == []


class _Writer:
    def __init__(self, opened=True):
        self.frames, self.opened = [], opened

    def isOpened(self):  # noqa: N802 - OpenCV's name
        return self.opened

    def write(self, frame):
        self.frames.append(frame)

    def release(self):
        pass


def test_an_unopened_video_writer_is_an_error(tmp_path):
    from je_auto_control.utils.video_report.video_report import write_step_video
    with pytest.raises(OSError):
        write_step_video([{"image": "x", "caption": "c"}], str(tmp_path / "v.mp4"), size=(1, 1),
                         loader=lambda image: image, drawer=lambda f, *a: f,
                         writer_factory=lambda *a: _Writer(opened=False))


def test_frames_are_resized_and_the_caller_array_is_untouched(tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from je_auto_control.utils.video_report.video_report import write_step_video
    small, large = np.zeros((120, 160, 3), np.uint8), np.zeros((240, 320, 3), np.uint8)
    writer = _Writer()
    write_step_video([{"image": small, "caption": "a"}, {"image": large, "caption": "b"}],
                     str(tmp_path / "v.mp4"), fps=1, seconds_per_step=1,
                     writer_factory=lambda *a: writer)
    assert {frame.shape for frame in writer.frames} == {(120, 160, 3)}
    assert not small.any(), "the caption was drawn on a copy"


def test_welch_with_no_variance_and_different_means():
    result = welch_t_test([1, 1], [5, 5])
    assert (result["p_value"], result["ci_low"], result["ci_high"]) == (0.0, 4.0, 4.0)


def test_negative_token_counts_are_refused(tmp_path):
    with pytest.raises(ValueError):
        CostStore(str(tmp_path / "c.jsonl")).record(provider="p", model="m",
                                                    input_tokens=-1000, output_tokens=10)
