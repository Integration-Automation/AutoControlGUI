"""Round-3 GUI audit regressions: Actions-menu slots must contain framework
exceptions instead of letting them escape into the Qt event loop.

* builder_tab / main_widget slots caught only builtin exception types while
  their callees raise ``AutoControl*Exception`` (finding 6);
* the auto-click ``_do_click`` slot skipped ``timer.stop()`` on a throwing
  backend, so the QTimer fired forever (finding 7);
* ``TestSuiteTab._on_load_file`` read a file with no error handling, so a
  non-UTF-8 file escaped the slot (finding 10).

Each slot is exercised on a lightweight stub ``self`` with the callee
monkeypatched to fail, so no full Qt widget tree is constructed.
"""
import os
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from je_auto_control.utils.exception.exceptions import (  # noqa: E402
    AutoControlExecuteActionException, AutoControlHTMLException,
    AutoControlMouseException,
)


def _raiser(exc):
    def _fn(*_args, **_kwargs):
        raise exc
    return _fn


# --- Finding 6: builder_tab._on_run ----------------------------------------

def test_builder_run_slot_surfaces_autocontrol_exception(monkeypatch):
    import je_auto_control.gui.script_builder.builder_tab as bt
    warned = {}
    monkeypatch.setattr(bt.QMessageBox, "warning",
                        lambda *a, **k: warned.setdefault("hit", True))
    monkeypatch.setattr(
        bt, "execute_action",
        _raiser(AutoControlExecuteActionException("unregistered command")),
    )

    tree = types.SimpleNamespace(root_steps=lambda: [bt.Step(command="AC_ok")])
    result = types.SimpleNamespace(setPlainText=lambda _s: None)
    stub = types.SimpleNamespace(_tree=tree, _result=result)

    bt.ScriptBuilderTab._on_run(stub)  # must not raise
    assert warned.get("hit")


# --- Finding 6: main_widget record / script slots --------------------------

def test_playback_record_slot_surfaces_autocontrol_exception(monkeypatch):
    import je_auto_control.gui.main_widget as mw
    warned = {}
    monkeypatch.setattr(mw.QMessageBox, "warning",
                        lambda *a, **k: warned.setdefault("hit", True))
    monkeypatch.setattr(
        mw, "execute_action",
        _raiser(AutoControlExecuteActionException("boom")),
    )
    stub = types.SimpleNamespace(_record_data=[["AC_ok"]])

    mw.AutoControlGUIWidget._playback_record(stub)  # must not raise
    assert warned.get("hit")


def test_execute_script_slot_surfaces_autocontrol_exception(monkeypatch):
    import je_auto_control.gui.main_widget as mw
    captured = {}
    monkeypatch.setattr(mw, "read_action_json", lambda _p: [["AC_ok"]])
    monkeypatch.setattr(
        mw, "execute_action",
        _raiser(AutoControlExecuteActionException("boom")),
    )
    editor = types.SimpleNamespace(text=lambda: "some.json")
    result = types.SimpleNamespace(setText=lambda s: captured.__setitem__("t", s))
    stub = types.SimpleNamespace(script_path_input=editor,
                                 script_result_text=result)

    mw.AutoControlGUIWidget._execute_script(stub)  # must not raise
    assert captured.get("t", "").startswith("Error")


# --- Finding 6: report tab, zero records -----------------------------------

def test_report_gen_html_slot_surfaces_autocontrol_exception():
    from je_auto_control.gui._report_tab import ReportTabMixin
    from je_auto_control.utils.test_record.record_test_class import (
        test_record_instance,
    )
    test_record_instance.test_record_list.clear()  # zero records -> raises
    captured = {}
    stub = types.SimpleNamespace(
        report_name_input=types.SimpleNamespace(text=lambda: "rpt"),
        report_result_text=types.SimpleNamespace(
            setText=lambda s: captured.__setitem__("t", s),
        ),
    )

    ReportTabMixin._gen_html(stub)  # must not raise AutoControlHTMLException
    assert captured.get("t", "").startswith("Error")


def test_report_generate_html_report_really_raises_on_zero_records():
    # Guards the assumption behind the slot test above.
    from je_auto_control.utils.generate_report.generate_html_report import (
        generate_html_report,
    )
    from je_auto_control.utils.test_record.record_test_class import (
        test_record_instance,
    )
    test_record_instance.test_record_list.clear()
    with pytest.raises(AutoControlHTMLException):
        generate_html_report("unused")


# --- Finding 7: auto-click timer stops on a throwing backend ---------------

def test_do_click_stops_timer_on_backend_exception(monkeypatch):
    import je_auto_control.gui._auto_click_tab as ac
    monkeypatch.setattr(ac.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(
        ac, "click_mouse",
        _raiser(AutoControlMouseException("no backend")),
    )
    stops = {"n": 0}
    stub = types.SimpleNamespace(
        click_type_combo=types.SimpleNamespace(currentIndex=lambda: 0),
        mouse_radio=types.SimpleNamespace(isChecked=lambda: True),
        mouse_button_combo=types.SimpleNamespace(currentText=lambda: "mouse_left"),
        cursor_x_input=types.SimpleNamespace(text=lambda: "0"),
        cursor_y_input=types.SimpleNamespace(text=lambda: "0"),
        timer=types.SimpleNamespace(stop=lambda: stops.__setitem__("n", stops["n"] + 1)),
    )

    ac.AutoClickTabMixin._do_click(stub)  # must not raise
    assert stops["n"] == 1  # the failing auto-click QTimer was stopped


# --- Finding 10: suite load-file tolerates a bad file ----------------------

def test_suite_load_file_handles_non_utf8(monkeypatch, tmp_path):
    import je_auto_control.gui.test_suite_tab as ts
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"\xff\xfe\x00 not valid utf-8 \xff")
    monkeypatch.setattr(ts.QFileDialog, "getOpenFileName",
                        lambda *a, **k: (str(bad), ""))
    captured = {}
    stub = types.SimpleNamespace(
        _spec=types.SimpleNamespace(setPlainText=lambda _s: captured.__setitem__("spec", True)),
        _summary=types.SimpleNamespace(setText=lambda s: captured.__setitem__("summary", s)),
    )

    ts.TestSuiteTab._on_load_file(stub)  # must not raise UnicodeDecodeError
    assert "summary" in captured  # error surfaced on the summary label
    assert "spec" not in captured  # the unreadable content was not shown
