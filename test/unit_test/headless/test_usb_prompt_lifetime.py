"""The USB prompt dialog must die by reference count, never by the cycle collector.

``TranslatableMixin._tr(self, ...)`` stored the widget in its own registry, so
every ``UsbPassthroughPromptDialog`` was a reference cycle: dropped, it stayed
alive as garbage — a parentless top-level window Python still owned — until the
cycle collector happened to run, and the collector then ran the C++ destructor
wherever it was standing.

On Python 3.10 and 3.11 the collector runs *inside* any allocation, including
the ones PySide makes while it converts the ``QList<QWidget*>`` returned by
``QApplication.topLevelWidgets()`` into a Python list. A collection there
destroys widgets whose pointers are still in the list being converted, and the
next element is a freed object: SIGSEGV with no Python-level cause. That killed
the 3.10 Linux and macOS squares inside ``test_usb_acl_prompt.py``'s dialog
driver, which scanned ``topLevelWidgets()`` from a timer. (3.12+ only collects
between bytecodes, so the same garbage is harmless there.)
"""
import gc
import os
import subprocess  # nosec B404  # reason: runs this test's own probe script
import sys
import textwrap
import threading
import time
import weakref
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
# gui/__init__.py loads main_window -> webrtc_panel -> aiortc.
pytest.importorskip("av")
pytest.importorskip("aiortc")

from PySide6.QtWidgets import QApplication, QDialog, QWidget  # noqa: E402

from je_auto_control.gui._i18n_helpers import TranslatableMixin  # noqa: E402
from je_auto_control.gui.language_wrapper.multi_language_wrapper import (  # noqa: E402
    language_wrapper,
)
from je_auto_control.gui.usb_passthrough_prompt import (  # noqa: E402
    PromptBridge, UsbPassthroughPromptDialog,
)
from je_auto_control.utils.usb.passthrough import UsbAcl  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[3]
_QUALITY_YML = _REPO_ROOT / ".github" / "workflows" / "quality.yml"


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def no_cycle_collector():
    """Reference counting only, so 'it was freed' cannot mean 'the collector got to it'."""
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()


class _Titled(TranslatableMixin, QWidget):
    """The smallest widget that registers itself for retranslation."""

    def __init__(self):
        super().__init__()
        self._tr_init()
        self._tr(self, "usb_prompt_title", setter="setWindowTitle")


def test_registering_itself_does_not_make_a_widget_a_cycle(qapp, no_cycle_collector):
    widget = _Titled()
    alive = weakref.ref(widget)
    del widget
    assert alive() is None


def test_a_widget_that_registered_itself_is_still_retranslated(qapp, monkeypatch):
    widget = _Titled()
    monkeypatch.setattr(language_wrapper, "translate", lambda key, default=None: f"<{key}>")
    widget.retranslate()
    assert widget.windowTitle() == "<usb_prompt_title>"


def test_a_dropped_prompt_dialog_is_freed_at_once(qapp, no_cycle_collector):
    dialog = UsbPassthroughPromptDialog(
        vendor_id="1050", product_id="0407", serial=None, viewer_id=None,
    )
    alive = weakref.ref(dialog)
    del dialog
    assert alive() is None


_WORKERS = 4
_DECISIONS_EACH = 25


def _answer_by_product(seen):
    """An ``exec`` that allows even product ids, remembers them, and records the dialog."""
    def answer(dialog):
        seen.append(weakref.ref(dialog))
        allow = int(dialog._product_id, 16) % 2 == 0  # noqa: SLF001
        dialog._remember_check.setChecked(allow)  # noqa: SLF001
        return QDialog.DialogCode.Accepted if allow else QDialog.DialogCode.Rejected
    return answer


def test_many_workers_get_their_own_verdicts_and_leave_no_dialog(
        qapp, monkeypatch, tmp_path, no_cycle_collector):
    seen = []
    monkeypatch.setattr(UsbPassthroughPromptDialog, "exec", _answer_by_product(seen))
    acl = UsbAcl(path=tmp_path / "acl.json")
    bridge = PromptBridge(acl=acl)
    verdicts = {}

    def work(worker_index):
        for step in range(_DECISIONS_EACH):
            product = f"{worker_index * _DECISIONS_EACH + step:04x}"
            verdicts[product] = bridge.decide(
                "1050", product, None, viewer_id=f"vw-{worker_index}", wait_timeout_s=20.0,
            )

    workers = [threading.Thread(target=work, args=(index,), daemon=True)
               for index in range(_WORKERS)]
    for worker in workers:
        worker.start()
    deadline = time.monotonic() + 30.0
    while any(worker.is_alive() for worker in workers) and time.monotonic() < deadline:
        qapp.processEvents()
        workers[0].join(0.005)
    assert not any(worker.is_alive() for worker in workers), "a decision never came back"

    total = _WORKERS * _DECISIONS_EACH
    assert verdicts == {f"{n:04x}": n % 2 == 0 for n in range(total)}
    assert sorted(rule.product_id for rule in acl.list_rules()) == \
        [f"{n:04x}" for n in range(0, total, 2)]
    # No flush of deferred deletes and no collection has run: each dialog went
    # when its slot returned, on the GUI thread, not later and not elsewhere.
    assert len(seen) == total
    # The last slot can still be unwinding when the last worker is seen dead,
    # so the event loop gets a moment; the collector stays off throughout.
    settle_until = time.monotonic() + 5.0
    while any(ref() is not None for ref in seen) and time.monotonic() < settle_until:
        qapp.processEvents()
        time.sleep(0.01)
    assert [ref for ref in seen if ref() is not None] == []


# What the 3.10 squares died of, made deterministic: prompt dialogs dropped the
# way a test or a caller drops them, a top-level window Python has never
# wrapped (so converting the list allocates), and a collection that is due.
_COLLECTION_PROBE = textwrap.dedent("""
    import faulthandler, gc, os
    faulthandler.enable()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication, QComboBox
    from je_auto_control.gui.usb_passthrough_prompt import UsbPassthroughPromptDialog
    app = QApplication([])
    combos = [QComboBox() for _ in range(20)]
    for combo in combos:
        combo.view()    # Qt builds the popup container; no Python wrapper exists
    gc.collect()
    gc.disable()
    for _ in range(400):
        UsbPassthroughPromptDialog(vendor_id="1050", product_id="0407", serial=None, viewer_id=None)
    scan = QApplication.topLevelWidgets
    gc.enable()
    widgets = scan()
    gc.disable()
    print("prompts-left", sum(isinstance(w, UsbPassthroughPromptDialog) for w in widgets))
""")


def test_a_due_collection_inside_a_widget_scan_finds_no_prompt_to_destroy():
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT), QT_QPA_PLATFORM="offscreen")
    argv = [sys.executable, "-c", _COLLECTION_PROBE]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=180, env=env, cwd=str(_REPO_ROOT), check=False)  # nosec B603  # nosemgrep  # reason: this test's own probe, fixed argv
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == "prompts-left 0"


def test_ci_keeps_the_fault_dump_outside_pytests_own_window():
    """pytest's faulthandler is off before collection and after unconfigure; the variable is not."""
    workflow = _QUALITY_YML.read_text(encoding="utf-8")
    assert 'PYTHONFAULTHANDLER: "1"' in workflow
