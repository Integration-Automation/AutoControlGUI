"""Assertions tab: run a single screen-state assertion and show pass/fail.

Thin wrapper over the headless ``je_auto_control.assert_*`` functions.
Assertions run with ``raise_on_fail=False`` so the GUI reports the
outcome instead of crashing the tab.
"""
import functools
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit,
    QVBoxLayout, QWidget,
)

from je_auto_control.gui._dispose import release_resources
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui._tab_task import TabTask
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
    language_wrapper,
)
import je_auto_control as ac

_KINDS = ("text", "image", "pixel", "window", "vlm")


def _t(key: str) -> str:
    return language_wrapper.translate(key, key)


def _parse_ints(raw: str) -> List[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


class AssertionsTab(TranslatableMixin, QWidget):
    """Form that drives one assertion and renders its :class:`AssertionResult`."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tr_init()
        self._kind = QComboBox()
        self._kind.addItems([_t(f"assert_kind_{k}") for k in _KINDS])
        self._kind.currentIndexChanged.connect(self._sync_visibility)
        self._target = QLineEdit()
        self._xy = QLineEdit()
        self._xy.setPlaceholderText("100, 200")
        self._rgb = QLineEdit()
        self._rgb.setPlaceholderText("255, 255, 255")
        self._expect = QCheckBox(_t("assert_expect_present"))
        self._expect.setChecked(True)
        self._regex = QCheckBox(_t("assert_regex"))
        self._result = QLabel()
        self._result.setWordWrap(True)
        self._runs = TabTask(self)
        self._runs.result.connect(self._show_result)
        self._runs.error.connect(self._show_error)
        self._build_layout()
        self._sync_visibility()

    def _build_layout(self) -> None:
        # The run command runs from the Actions menu; the tab keeps only
        # the assertion form and the result label.
        root = QVBoxLayout(self)
        krow = QHBoxLayout()
        krow.addWidget(QLabel(_t("assert_kind")))
        krow.addWidget(self._kind)
        krow.addStretch()
        root.addLayout(krow)

        self._target_label = QLabel(_t("assert_target"))
        root.addWidget(self._target_label)
        root.addWidget(self._target)

        self._xy_label = QLabel(_t("assert_pixel_xy"))
        root.addWidget(self._xy_label)
        root.addWidget(self._xy)
        self._rgb_label = QLabel(_t("assert_pixel_rgb"))
        root.addWidget(self._rgb_label)
        root.addWidget(self._rgb)

        root.addWidget(self._expect)
        root.addWidget(self._regex)
        root.addWidget(self._result)
        root.addStretch()

    def dispose(self) -> None:
        """Release what the tab holds beyond its widgets: the command still running in the background.

        A script run is stopped; other work cannot be interrupted, so it runs to its end and its
        result is dropped. Called by ``close_tab(key, release=True)``; safe to call twice.
        """
        release_resources(self)

    def menu_actions(self) -> list:
        """Expose tab commands to the window-level Actions menu."""
        return [
            ("assert_run", self._on_run),
        ]

    def _current_kind(self) -> str:
        return _KINDS[self._kind.currentIndex()]

    def _sync_visibility(self) -> None:
        kind = self._current_kind()
        is_pixel = kind == "pixel"
        for widget in (self._xy_label, self._xy, self._rgb_label, self._rgb):
            widget.setVisible(is_pixel)
        for widget in (self._target_label, self._target):
            widget.setVisible(not is_pixel)
        self._regex.setVisible(kind == "text")

    def _request(self) -> Dict[str, Any]:
        """What the fields ask for, as plain values the worker can use."""
        return {"kind": self._current_kind(), "present": self._expect.isChecked(),
                "target": self._target.text(), "regex": self._regex.isChecked(),
                "xy": self._xy.text(), "rgb": self._rgb.text()}

    def _on_run(self) -> None:
        # OCR, a template search or a VLM call: off the GUI thread, one at a time.
        if not self._runs.start(functools.partial(_run_assertion, self._request())):
            return
        self._result.setText(_t("task_running"))

    def _show_error(self, error: object) -> None:
        self._result.setText(f"{_t('assert_failed')}: {error}")

    def _show_result(self, result: Dict[str, Any]) -> None:
        label = _t("assert_passed") if result["passed"] else _t("assert_failed")
        self._result.setText(f"{label} — {result['message']}")


def _run_assertion(request: Dict[str, Any]) -> Dict[str, Any]:
    """Worker thread: run the assertion the tab's fields described."""
    kind, present, target = request["kind"], request["present"], request["target"]
    if kind == "text":
        return ac.assert_text(target, regex=request["regex"], present=present,
                              raise_on_fail=False).to_dict()
    if kind == "image":
        return ac.assert_image(target, present=present, raise_on_fail=False).to_dict()
    if kind == "pixel":
        coords = _parse_ints(request["xy"])
        if len(coords) < 2:
            # Unpacking a short list used to reach assert_pixel with the
            # RGB list bound to `y`, and the user saw a TypeError about
            # keyword arguments instead of what they typed wrong.
            raise ValueError(f"pixel assertion needs 'x,y'; got {request['xy']!r}")
        return ac.assert_pixel(coords[0], coords[1], _parse_ints(request["rgb"]),
                               match=present, raise_on_fail=False).to_dict()
    if kind == "window":
        return ac.assert_window(target, exists=present, raise_on_fail=False).to_dict()
    return ac.assert_by_description(target, present=present, raise_on_fail=False).to_dict()
