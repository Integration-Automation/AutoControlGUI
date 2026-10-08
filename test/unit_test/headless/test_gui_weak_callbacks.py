"""A background task's callbacks do not keep the tab that started it alive (offscreen Qt, fakes only).

A task handle and the relay under it are descendants of the tab. A callback
held strongly by one of them -- ``functools.partial(self.x, ...)``, a lambda or
a nested function -- made the handle the last holder of a parentless tab, which
was then destroyed from inside the destructor of its own grandchild: an abort
with no traceback. The behaviour tests drop the only reference while the work
is still out and expect the tab to be freed at once; the source rule fails a
new strong connection.
"""
import ast
import functools
import gc
import os
import pathlib
import threading
import weakref

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from je_auto_control.gui import _weak_call  # noqa: E402
from je_auto_control.gui._weak_call import WeakCall, weak_slot  # noqa: E402
from je_auto_control.gui._worker_thread import CallWorker, start_worker  # noqa: E402
from headless._qt_settle import pump_until  # noqa: E402

_GUI_DIR = pathlib.Path(_weak_call.__file__).resolve().parent


@pytest.fixture(autouse=True)
def qapp(monkeypatch):
    app = QApplication.instance() or QApplication([])
    for box in ("warning", "information", "question", "critical"):
        monkeypatch.setattr(QMessageBox, box, lambda *args: None)
    yield app


class _Gate:
    """Work that waits on the worker thread until the test lets it go."""

    def __init__(self, value=None):
        self.entered, self.release, self.value = threading.Event(), threading.Event(), value

    def __call__(self, *_args):
        self.entered.set()
        self.release.wait(30.0)
        return self.value


def _freed_while_out(start):
    """Drop the owner ``start()`` returns while its gate still runs; return whether that freed it."""
    owner, gate = start()
    seen = weakref.ref(owner)
    del owner
    gc.collect()
    freed = seen() is None
    gate.release.set()
    assert gate.entered.wait(10.0)
    pump_until(lambda: False, timeout=0.2)      # the outcome has nobody to go to, and nothing crashes
    return freed


# --- the helper --------------------------------------------------------------------------------------------------

class _Target:
    def __init__(self):
        self.seen = []

    def take(self, *args, **kwargs):
        self.seen.append((args, kwargs))


def test_a_bound_method_is_held_weakly_with_its_leading_arguments():
    target = _Target()
    call = WeakCall(target.take, ("a",))
    assert call("value") is True and target.seen == [(("a", "value"), {})]
    del target
    gc.collect()
    assert call("late") is False


def test_a_partial_of_a_bound_method_is_taken_apart():
    target = _Target()
    call = WeakCall(functools.partial(functools.partial(target.take, 1, key="k"), 2), (3,))
    seen = weakref.ref(target)
    assert call(4) is True and target.seen == [((1, 2, 3, 4), {"key": "k"})]
    del target
    gc.collect()
    assert seen() is None and call(5) is False


def test_a_plain_function_and_none_are_accepted():
    seen = []
    assert WeakCall(seen.append)("x") is True and seen == ["x"]
    assert WeakCall(None)("x") is False
    slot = weak_slot(seen.append)
    slot("y")
    assert seen == ["x", "y"]


# --- the places that deliver a task's outcome --------------------------------------------------------------------

class _Tab(QWidget):
    def __init__(self):
        super().__init__()
        self.outcomes = []

    def done(self, *args):
        self.outcomes.append(args)

    def ended(self):
        self.outcomes.append("ended")


def test_a_worker_does_not_keep_its_tab_alive(qapp):
    def start():
        tab, gate = _Tab(), _Gate()
        start_worker(tab, CallWorker(gate), on_done=functools.partial(tab.done, "tag"),
                     on_fail=tab.done, on_thread_done=tab.ended)
        return tab, gate

    assert _freed_while_out(start)


def test_a_worker_still_delivers_to_a_tab_that_is_there(qapp):
    tab, gate = _Tab(), _Gate("value")
    start_worker(tab, CallWorker(gate), on_done=functools.partial(tab.done, "tag"),
                 on_fail=tab.done, on_thread_done=tab.ended)
    gate.release.set()
    assert pump_until(lambda: "ended" in tab.outcomes)
    assert tab.outcomes == [("tag", "value"), "ended"]
    tab.deleteLater()


def test_a_panel_task_does_not_keep_its_panel_alive(qapp):
    from je_auto_control.gui.remote_desktop.webrtc_panel_common import start_panel_task

    def start():
        panel, gate = _Tab(), _Gate()
        panel._file_task = None
        assert start_panel_task(panel, "_file_task", gate, functools.partial(panel.done, "path"), panel.done)
        return panel, gate

    assert _freed_while_out(start)


def test_a_panel_task_clears_its_attribute_and_delivers(qapp):
    from je_auto_control.gui.remote_desktop.webrtc_panel_common import start_panel_task
    panel, gate = _Tab(), _Gate(3)
    panel._file_task = None
    assert start_panel_task(panel, "_file_task", gate, functools.partial(panel.done, "path"), panel.done)
    assert not start_panel_task(panel, "_file_task", gate, panel.done, panel.done)     # one at a time
    gate.release.set()
    assert pump_until(lambda: panel._file_task is None)
    assert panel.outcomes == [("path", 3)]
    panel.deleteLater()


class _Viewer:
    def __init__(self, gate):
        self._gate = gate

    def connect(self, timeout=None):
        self._gate()

    def disconnect(self):
        """Nothing to close."""


def test_a_pending_connect_does_not_keep_its_panel_alive(qapp):
    from je_auto_control.gui.remote_desktop._connect_task import connect_viewer

    def start():
        panel, gate = _Tab(), _Gate()
        connect_viewer(panel, _Viewer(gate), on_connected=functools.partial(panel.done, "slot"),
                       on_failed=panel.done)
        return panel, gate

    assert _freed_while_out(start)


def _host_panel_part(gate):
    pytest.importorskip("aiortc", exc_type=ImportError)
    from je_auto_control.gui.remote_desktop.webrtc_host_connection import _HostConnectionMixin

    class _FakeHost:
        def create_session_offer(self):
            return gate()

        def stop_session(self, _session_id):
            """Nothing to stop."""

    class _Part(_HostConnectionMixin):
        def __init__(self):
            super().__init__()
            self._multi_host = _FakeHost()
            self.shown = []

        def _show_offer(self, host, outcome):
            self.shown.append((host, outcome))

    return _Part()


def test_an_offer_being_made_does_not_keep_the_host_panel_alive(qapp):
    def start():
        gate = _Gate(("session", "offer"))
        part = _host_panel_part(gate)
        part._produce_offer()
        return part, gate

    assert _freed_while_out(start)


def test_an_offer_still_reaches_a_host_panel_that_is_there(qapp):
    gate = _Gate(("session", "offer"))
    part = _host_panel_part(gate)
    part._produce_offer()
    gate.release.set()
    assert pump_until(lambda: bool(part.shown))
    assert part.shown == [(part._multi_host, ("session", "offer"))]
    part.deleteLater()


def _viewer_panel_part(gate):
    pytest.importorskip("aiortc", exc_type=ImportError)
    from je_auto_control.gui.remote_desktop.webrtc_viewer_connection import _ViewerConnectionMixin

    class _FakeViewer:
        def process_offer(self, _offer, expected_dtls_fingerprint=None):
            return gate()

    class _Part(_ViewerConnectionMixin):
        def __init__(self):
            super().__init__()
            self._viewer = _FakeViewer()
            self.answers = []

        def _show_manual_answer(self, answer):
            self.answers.append(answer)

    return _Part()


def test_an_answer_being_made_does_not_keep_the_viewer_panel_alive(qapp):
    def start():
        gate = _Gate("answer")
        part = _viewer_panel_part(gate)
        part._produce_answer("offer")
        return part, gate

    assert _freed_while_out(start)


def test_an_answer_reaches_the_viewer_panel_only_while_its_viewer_is_current(qapp):
    gate = _Gate("answer")
    part = _viewer_panel_part(gate)
    part._produce_answer("offer")
    gate.release.set()
    assert pump_until(lambda: bool(part.answers))
    assert part.answers == ["answer"]
    late = _Gate("late")
    part._viewer = type(part._viewer)()
    part._viewer.process_offer = lambda _offer, expected_dtls_fingerprint=None: late()
    part._produce_answer("offer")
    part._viewer = None                         # stopped while the answer was being made
    late.release.set()
    pump_until(lambda: False, timeout=0.3)
    assert part.answers == ["answer"]
    part.deleteLater()


# --- no new strong connection ------------------------------------------------------------------------------------

#: Signals of a task handle. A lambda on a signal of this name is refused whatever emits it.
_TASK_SIGNALS = {"result", "error", "finished", "progress"}
#: Helpers that deliver a task's outcome, and where their callbacks sit (keywords, first positional index).
_DELIVERERS = {
    "start_worker": ({"on_done", "on_fail", "on_thread_done"}, None),
    "connect_viewer": ({"on_connected", "on_failed"}, None),
    "start_panel_task": (set(), 3),
    "_run_async": (set(), 1),
    "_run_off_gui_thread": (set(), 1),
    "run": ({"on_done", "on_error"}, None),
    "retire": ({"on_done"}, None),
}


def _is_self_partial(node):
    """``functools.partial(self.x, ...)`` / ``partial(self.x, ...)``."""
    if not (isinstance(node, ast.Call) and node.args):
        return False
    name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
    first = node.args[0]
    while isinstance(first, ast.Attribute):
        first = first.value
    return name == "partial" and isinstance(first, ast.Name) and first.id == "self"


def _callee(node):
    return node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")


class _Finder(ast.NodeVisitor):
    """Collects strong callbacks handed to a task's signal or to a helper that delivers its outcome."""

    def __init__(self, name):
        self.name, self.found, self._nested = name, [], [set()]

    def visit_FunctionDef(self, node):  # noqa: N802  # reason: ast.NodeVisitor's naming
        nested = {child.name for child in ast.walk(node)
                  if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child is not node}
        self._nested.append(nested)
        self.generic_visit(node)
        self._nested.pop()

    def _strong(self, node, in_connect):
        if isinstance(node, ast.Lambda):
            return "a lambda"
        if isinstance(node, ast.Name) and node.id in self._nested[-1]:
            return f"the nested function {node.id}"
        if in_connect and _is_self_partial(node):
            return "a partial of a method of self"
        return ""

    def _report(self, node, argument, in_connect):
        why = self._strong(argument, in_connect)
        if why:
            self.found.append(f"{self.name}:{node.lineno}: {why}")

    def visit_Call(self, node):  # noqa: N802  # reason: ast.NodeVisitor's naming
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr == "connect" and isinstance(func.value, ast.Attribute)
                and func.value.attr in _TASK_SIGNALS):
            for argument in node.args:
                self._report(node, argument, True)
        keywords, first = _DELIVERERS.get(_callee(node), (set(), None))
        for keyword in node.keywords:
            if keyword.arg in keywords:
                self._report(node, keyword.value, False)
        if first is not None:
            for argument in node.args[first:]:
                self._report(node, argument, False)
        self.generic_visit(node)


def _strong_callbacks(path):
    finder = _Finder(path.relative_to(_GUI_DIR).as_posix())
    finder.visit(ast.parse(path.read_text(encoding="utf-8")))
    return finder.found


def test_no_task_outcome_goes_to_a_callback_that_holds_the_tab():
    files = sorted(_GUI_DIR.rglob("*.py"))
    assert len(files) > 100
    found = [hit for path in files for hit in _strong_callbacks(path)]
    assert found == [], ("pass a method (and its arguments) through weak_slot / the helper instead; "
                         f"see gui/_weak_call.py: {found}")


def test_the_rule_sees_each_strong_form_and_accepts_the_weak_one(tmp_path):
    sample = tmp_path / "sample_tab.py"
    sample.write_text(
        "import functools\n"
        "class Tab:\n"
        "    def go(self):\n"
        "        def deliver(value):\n"
        "            self.show(value)\n"
        "        task = submit()\n"
        "        task.result.connect(deliver)\n"
        "        task.error.connect(lambda error: self.show(error))\n"
        "        task.finished.connect(functools.partial(self.show, 1))\n"
        "        task.result.connect(weak_slot(self.show, 1))\n"
        "        task.finished.connect(self.show)\n"
        "        start_worker(self, worker, on_done=lambda value: self.show(value), on_thread_done=self.show)\n"
        "        start_worker(self, worker, on_done=functools.partial(self.show, 1), on_thread_done=self.show)\n"
        "        start_panel_task(self, '_task', work, deliver, self.show)\n"
        "        self._run_async(lambda: fetch(), lambda value: self.show(value), self.show)\n",
        encoding="utf-8")
    finder = _Finder("sample_tab.py")
    finder.visit(ast.parse(sample.read_text(encoding="utf-8")))
    assert [hit.split(":", 1)[1] for hit in finder.found] == [
        "7: the nested function deliver", "8: a lambda", "9: a partial of a method of self",
        "12: a lambda", "14: the nested function deliver", "15: a lambda"]
