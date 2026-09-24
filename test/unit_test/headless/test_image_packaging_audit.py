"""Image-analysis / packaging defects from the 2026-09-24 audit.

CVD simulation used gamma-space Coblis matrices; squares read as radio
buttons and hollow text fields as toggles; step repair acted again after
escalating or on an already-changed screen; the SBOM listed a package twice
and installed extras; the registry manifest's description was too long for
the schema; generated stubs dropped the keyword-only marker and could be
broken by a docstring; provenance verification passed with nothing checked;
"3.14" counted as two sentences; wide SimHashes were silently truncated.
"""
import ast
import inspect

import pytest

from je_auto_control.utils.cvd_simulate.cvd_simulate import simulate_cvd
from je_auto_control.utils.icon_classify.icon_classify import classify_widget
from je_auto_control.utils.mcp_registry import registry
from je_auto_control.utils.near_dup.near_dup import simhash
from je_auto_control.utils.provenance.provenance import (
    build_provenance, subject_for_bytes, verify_provenance,
)
from je_auto_control.utils.readability.readability import readability_stats
from je_auto_control.utils.sbom import sbom
from je_auto_control.utils.step_repair.step_repair import run_with_repair
from je_auto_control.utils.stubs import generator


@pytest.mark.parametrize("rgb, expected", [
    ((255, 0, 0), (163, 145, 0)), ((0, 128, 0), (119, 106, 24)),
])
def test_deuteranopia_follows_machado_in_linear_rgb(rgb, expected):
    result = simulate_cvd(rgb, "deuteranopia")
    assert all(abs(a - b) <= 2 for a, b in zip(result, expected))
    assert simulate_cvd((10, 200, 30), "protanopia", severity=0.0) == (10, 200, 30)


def test_squares_and_hollow_boxes_are_not_radios_or_toggles():
    square = {"aspect": 1.0, "circularity": 0.785, "fill": 0.09, "vertices": 4}
    circle = {"aspect": 1.0, "circularity": 0.83, "fill": 0.06, "vertices": 8}
    hollow = {"aspect": 2.6, "circularity": 0.59, "fill": 0.05, "vertices": 4}
    pill = {"aspect": 2.6, "circularity": 0.59, "fill": 0.57, "vertices": 8}
    assert classify_widget(square) == "checkbox"
    assert classify_widget(circle) == "radio"
    assert classify_widget(hollow) == "text_field"
    assert classify_widget(pill) == "toggle"


def test_escalation_ends_the_repair_and_changed_screens_are_not_re_acted():
    calls = []
    outcome = run_with_repair(lambda: calls.append("act"), lambda: False,
                              apply_tactic=calls.append, verdict_for=lambda: "changed_elsewhere")
    assert calls == ["act", "escalate"] and outcome.detail == "escalated"
    calls.clear()
    run_with_repair(lambda: calls.append("act"), lambda: False,
                    apply_tactic=calls.append, verdict_for=lambda: "changed")
    assert calls.count("act") == 1


def test_sbom_requirements_skip_extras_and_other_platforms():
    assert sbom._applies("requests>=2")
    assert not sbom._applies('PySide6; extra == "gui"')
    assert not sbom._applies('pyobjc; sys_platform == "no-such-platform"')


def test_the_registry_manifest_fits_the_schema():
    manifest = registry.build_server_manifest(version="1.0.0")
    assert len(manifest["description"]) <= 100
    with pytest.raises(ValueError):
        registry.build_server_manifest(version="1.0.0", description="x" * 101)


def test_stub_signatures_keep_keyword_only_and_positional_only_markers():
    def handler(a=1, /, b=2, *, c):  # noqa: ANN001 - fixture
        return a, b, c

    rendered = generator._render_parameters(inspect.signature(handler))
    ast.parse(f"def f({rendered}): ...")
    assert "/" in rendered and "*, c" in rendered


def test_a_docstring_cannot_break_the_stub():
    line = generator._render_docstring('Return "x"')
    ast.parse(f"def f():\n{line}")
    line = generator._render_docstring("path C:\\temp and \"\"\" quotes")
    ast.parse(f"def f():\n{line}")


def test_provenance_reports_subjects_nobody_checked():
    statement = build_provenance([subject_for_bytes("a.whl", b"a")])
    assert [m["name"] for m in verify_provenance(statement, {})] == ["a.whl"]
    with pytest.raises(ValueError, match="share names"):
        build_provenance([subject_for_bytes("x.whl", b"1"), subject_for_bytes("x.whl", b"2")])


def test_a_decimal_point_does_not_end_a_sentence():
    assert readability_stats("Pi is 3.14 today.")["sentences"] == 1


def test_simhash_bits_are_bounded():
    with pytest.raises(ValueError):
        simhash("some text", bits=128)
