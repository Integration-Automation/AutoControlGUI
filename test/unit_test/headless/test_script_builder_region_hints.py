"""Every Script Builder region hint names the convention its command reads.

The matchers, OCR and most vision commands capture through ``grab_logical``,
which takes ``[x, y, width, height]``; the colour, histogram and SSIM commands
through ``pil_screenshot``, which takes ``[left, top, right, bottom]``. The
hints said left, top, right, bottom for 25 of the first kind (and x, y, w, h
for one of the second), so a region typed as the hint asked searched another
rectangle. Each command is run here with both captures stubbed, and the
capture it reached is compared with its hint.
"""
import json

import numpy as np
import pytest
from PIL import Image

from je_auto_control.gui.script_builder import command_schema
from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS, FieldType
from je_auto_control.utils.cv2_utils import screenshot
from je_auto_control.utils.executor.action_executor import Executor
from je_auto_control.utils.monitor_layout import logical_frame
from je_auto_control.utils.ocr import ocr_engine

_HINTS = {
    command_schema._RECT_PLACEHOLDER: "xywh",
    command_schema._RECT4_PLACEHOLDER: "xywh",
    command_schema._REGION_PLACEHOLDER: "ltrb",
}

# The region never reaches either stubbed capture: pure grid geometry, a PIL
# ImageGrab bbox, or an OCR engine that has to be installed first.
_READ_FROM_THE_ADAPTER = {
    "AC_grid_cells": "ltrb", "AC_cell_for_point": "ltrb", "AC_point_for_cell": "ltrb",
    "AC_read_qr": "ltrb", "AC_region_color_stats": "ltrb", "AC_wait_color": "ltrb",
    "AC_ocr_to_var": "xywh",
}


_REGION = [10, 20, 30, 40]


def _region_hint(spec):
    return next((field.placeholder for field in spec.fields if field.name == "region"), None)


_REGION_COMMANDS = sorted(name for name, spec in COMMAND_SPECS.items() if _region_hint(spec) is not None)


def _arguments(spec, template):
    overrides = {
        "rgb": "[255, 0, 0]", "templates": json.dumps([template, template]), "boxes": "[[0, 0, 5, 5]]",
        "lower_hsv": "[0, 0, 0]", "upper_hsv": "[179, 255, 255]", "reference": template,
        "timeout_s": 0.0, "timeout": 0.0,
    }
    params = {"region": list(_REGION)}
    for field in spec.fields:
        if field.name in overrides:
            params[field.name] = overrides[field.name]
        elif field.name == "region" or field.optional:
            continue
        elif field.field_type == FieldType.FILE_PATH or field.name in ("template", "image", "source", "path"):
            params[field.name] = template
        elif field.default is not None:
            params[field.name] = field.default
        elif field.field_type == FieldType.INT:
            params[field.name] = 3
        elif field.field_type == FieldType.FLOAT:
            params[field.name] = 1.0
        else:
            params[field.name] = "x"
    return params


@pytest.fixture
def captures(monkeypatch, tmp_path):
    """Stub both capture entry points; yields (calls, template path)."""
    calls = []
    frame = Image.fromarray(np.random.default_rng(0).integers(0, 255, (200, 200, 3)).astype(np.uint8))

    # Only captures of the step's own region count: AC_wait_actionable also
    # samples the matched box, which it converts itself.
    def grab_logical(region=None, **_kwargs):
        if region is not None and list(region) == _REGION:
            calls.append("xywh")
        return frame, 0, 0

    def pil_screenshot(file_path=None, screen_region=None):
        if screen_region is not None and list(screen_region) == _REGION:
            calls.append("ltrb")
        return frame

    monkeypatch.setattr(logical_frame, "grab_logical", grab_logical)
    monkeypatch.setattr(ocr_engine, "grab_logical", grab_logical)
    monkeypatch.setattr(screenshot, "pil_screenshot", pil_screenshot)
    template = tmp_path / "template.png"
    Image.fromarray(np.asarray(frame)[20:40, 20:40]).save(template)
    yield calls, str(template)


def test_every_region_hint_is_a_named_convention():
    unnamed = {name: _region_hint(COMMAND_SPECS[name]) for name in _REGION_COMMANDS
               if _region_hint(COMMAND_SPECS[name]) not in _HINTS}
    assert not unnamed
    assert len(_REGION_COMMANDS) >= 40


@pytest.mark.parametrize("name", [name for name in _REGION_COMMANDS if name not in _READ_FROM_THE_ADAPTER])
def test_the_hint_matches_the_capture_the_command_reaches(name, captures):
    calls, template = captures
    Executor().execute_action([[name, _arguments(COMMAND_SPECS[name], template)]])
    assert calls, f"{name} reached neither capture; list it with the convention its adapter reads"
    assert set(calls) == {_HINTS[_region_hint(COMMAND_SPECS[name])]}


@pytest.mark.parametrize("name", sorted(_READ_FROM_THE_ADAPTER))
def test_commands_outside_the_captures_keep_their_listed_convention(name):
    assert _HINTS[_region_hint(COMMAND_SPECS[name])] == _READ_FROM_THE_ADAPTER[name]


def test_the_grid_commands_read_left_top_right_bottom():
    from je_auto_control.utils.screen_grid import grid_cells
    cell = grid_cells(1, 1, region=[10, 20, 30, 40])[0].to_dict()
    assert (cell["left"], cell["top"], cell["right"], cell["bottom"]) == (10, 20, 30, 40)
