"""Headless tests for the screenshot redaction layer."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from je_auto_control.utils.redaction import (
    POLICY_MODERATE, POLICY_OFF, POLICY_STRICT,
    RedactionEngine, RedactionPolicy, RedactionResult,
    default_policy, policy_from_name, redact_png_bytes,
)
from je_auto_control.utils.redaction.policies import (
    DETECTOR_CREDIT_CARD, DETECTOR_EMAIL, DETECTOR_SECURE_FIELD,
)
from je_auto_control.utils.redaction.rules import (
    merge_boxes, build_detector_chain, regex_detector,
    secure_field_detector,
)


# === policy lookup ==========================================================

def test_policy_from_name_case_insensitive():
    assert policy_from_name("STRICT") is POLICY_STRICT
    assert policy_from_name("moderate") is POLICY_MODERATE
    assert policy_from_name("off") is POLICY_OFF
    assert policy_from_name(None) is POLICY_OFF


def test_policy_from_name_unknown_raises():
    with pytest.raises(ValueError, match="unknown redaction policy"):
        policy_from_name("paranoid")


def test_default_policy_reads_env(monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_REDACTION", "strict")
    assert default_policy() is POLICY_STRICT
    monkeypatch.delenv("JE_AUTOCONTROL_REDACTION", raising=False)
    assert default_policy() is POLICY_OFF


# === rules ==================================================================

def test_email_regex_detector_matches_ocr_token():
    detector = regex_detector(DETECTOR_EMAIL)
    boxes = detector(None, {
        "ocr": [
            ("contact: ada@example.com", (10, 20, 200, 40)),
            ("nothing here", (10, 60, 200, 80)),
        ],
    })
    assert boxes == [(10, 20, 200, 40)]


def test_credit_card_regex_detector_handles_spaces():
    detector = regex_detector(DETECTOR_CREDIT_CARD)
    boxes = detector(None, {
        "ocr": [("4111 1111 1111 1111", (0, 0, 300, 30))],
    })
    assert boxes == [(0, 0, 300, 30)]


def test_secure_field_detector_uses_accessibility_tree():
    detector = secure_field_detector()
    boxes = detector(None, {
        "accessibility": [
            {"is_password": True, "bbox": [5, 5, 100, 25]},
            {"is_password": False, "bbox": [5, 30, 100, 50]},
        ],
    })
    assert boxes == [(5, 5, 100, 25)]


def test_secure_field_detector_skips_missing_bbox():
    detector = secure_field_detector()
    boxes = detector(None, {
        "accessibility": [{"is_password": True}],
    })
    assert boxes == []


def test_merge_boxes_collapses_overlapping_rects():
    merged = merge_boxes([(0, 0, 50, 50), (40, 40, 90, 90), (200, 200, 220, 220)])
    assert len(merged) == 2
    assert (0, 0, 90, 90) in merged
    assert (200, 200, 220, 220) in merged


def test_build_detector_chain_skips_unknown_names():
    chain = build_detector_chain(
        ["definitely_not_a_real_detector", DETECTOR_EMAIL],
        [(1, 2, 3, 4)],
    )
    # Two callables: the email regex + the static-region detector.
    assert len(chain) == 2


# === engine =================================================================

def _solid_image(size=(160, 80), color=(220, 220, 220)) -> Image.Image:
    return Image.new("RGB", size, color)


def test_engine_returns_original_when_no_matches():
    engine = RedactionEngine(POLICY_MODERATE)
    image = _solid_image()
    out, result = engine.redact_image(image, {"ocr": [], "accessibility": []})
    assert out is image
    assert result.boxes == ()


def test_engine_blurs_secure_field_bbox():
    engine = RedactionEngine(RedactionPolicy(
        detectors=(DETECTOR_SECURE_FIELD,),
        blur_radius=10,
    ))
    image = _solid_image()
    out, result = engine.redact_image(image, {
        "accessibility": [{"is_password": True, "bbox": [10, 10, 70, 50]}],
    })
    assert isinstance(out, Image.Image)
    assert result.boxes == ((10, 10, 70, 50),)


def test_engine_static_region_blur_changes_pixels():
    engine = RedactionEngine(RedactionPolicy(
        regions=((20, 20, 80, 60),),
        overlay_color=(0, 0, 0),
    ))
    image = _solid_image(color=(200, 200, 200))
    out, _ = engine.redact_image(image)
    pixel_in = out.getpixel((30, 30))
    pixel_out = out.getpixel((100, 30))
    assert pixel_in == (0, 0, 0)
    assert pixel_out == (200, 200, 200)


def test_redact_bytes_round_trips_png():
    image = _solid_image()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    png_bytes = buffer.getvalue()
    engine = RedactionEngine(RedactionPolicy(
        regions=((10, 10, 40, 40),),
        overlay_color=(0, 0, 0),
    ))
    out_bytes, result = engine.redact_bytes(png_bytes)
    assert out_bytes != png_bytes
    assert result.boxes == ((10, 10, 40, 40),)


def test_redact_png_bytes_convenience_helper(monkeypatch):
    image = _solid_image()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    monkeypatch.delenv("JE_AUTOCONTROL_REDACTION", raising=False)
    out_bytes, result = redact_png_bytes(
        buffer.getvalue(),
        policy=RedactionPolicy(regions=((0, 0, 20, 20),),
                                overlay_color=(255, 0, 0)),
    )
    assert result.boxes == ((0, 0, 20, 20),)
    assert out_bytes != buffer.getvalue()


# === executor + MCP wiring ==================================================

def test_executor_registers_ac_redact_screenshot():
    from je_auto_control.utils.executor.action_executor import executor
    assert "AC_redact_screenshot" in executor.known_commands()


def test_mcp_registry_exposes_ac_redact_screenshot():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert "ac_redact_screenshot" in names


def test_executor_round_trip_writes_redacted_file(tmp_path):
    from je_auto_control.utils.executor.action_executor import (
        _redact_screenshot,
    )
    src = tmp_path / "frame.png"
    out = tmp_path / "redacted.png"
    _solid_image((120, 80)).save(src, format="PNG")
    result = _redact_screenshot(
        file_path=str(src), output_path=str(out),
        policy="moderate", regions=[[5, 5, 50, 40]],
    )
    assert Path(result["output_path"]) == out
    assert out.exists()
    assert (5, 5, 50, 40) in [tuple(b) for b in result["boxes"]]


# === facade + Qt-free import ================================================

def test_facade_exports_redaction_surface():
    import je_auto_control as ac
    for name in ("RedactionEngine", "RedactionPolicy", "POLICY_STRICT",
                 "default_redaction_policy", "redact_png_bytes"):
        assert hasattr(ac, name), name


def test_package_facade_stays_qt_free():
    import subprocess
    import sys
    script = (
        "import sys, je_auto_control  # noqa: F401\n"
        "qt = [m for m in sys.modules if 'PySide6' in m]\n"
        "import json; print(json.dumps(qt))\n"
    )
    # nosemgrep
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", script],
        capture_output=True, text=True, check=True, timeout=60,
    )
    assert result.stdout.strip() in ("[]", "")
