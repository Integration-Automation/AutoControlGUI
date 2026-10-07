"""Translation registries must not defer parentless GUI destruction to a GC worker."""
import pytest

from headless._exit_probe import run_probe

pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)

_OWNERSHIP = r'''
import gc
import sys
import threading
import weakref
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTabWidget, QWidget
from je_auto_control.gui._i18n_helpers import TranslatableMixin
from je_auto_control.gui.usb_passthrough_prompt import UsbPassthroughPromptDialog

app = QApplication([])
gc.disable()
main_ident = threading.get_ident()
destroyed = []
if sys.argv[1] == 'dialog':
    owner = UsbPassthroughPromptDialog(vendor_id='1234', product_id='5678', serial=None, viewer_id=None)
else:
    class Tabs(TranslatableMixin, QTabWidget):
        pass
    owner = Tabs()
    owner._tr_init()
    owner.addTab(QWidget(), 'before')
    owner._tr_tab(owner, 0, 'tab-key')
owner.destroyed.connect(lambda *_args: destroyed.append(threading.get_ident()), Qt.ConnectionType.DirectConnection)
reference = weakref.ref(owner)
owner = None
worker = threading.Thread(target=gc.collect)
worker.start()
worker.join(5)
assert not worker.is_alive()
assert reference() is None
assert destroyed == [main_ident], ('GUI destruction escaped its owner thread', main_ident, destroyed)
'''

_TRANSLATION = r'''
import gc
import weakref
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QLabel, QWidget
from je_auto_control.gui import _i18n_helpers as helpers

app = QApplication([])
class Owner(helpers.TranslatableMixin, QWidget):
    pass
owner = Owner()
owner._tr_init()
with patch.object(helpers.language_wrapper, 'translate', side_effect=lambda key, _fallback: 'one:' + key):
    owner._tr(owner, 'title', setter='setWindowTitle')
    child = owner._tr(QLabel(), 'child')
    reference = weakref.ref(child)
    child = None
gc.collect()
assert reference() is not None, 'the registry must retain unparented child wrappers'
with patch.object(helpers.language_wrapper, 'translate', side_effect=lambda key, _fallback: 'two:' + key):
    owner.retranslate()
assert owner.windowTitle() == 'two:title'
assert reference().text() == 'two:child'
owner.deleteLater()
'''


@pytest.mark.parametrize('kind', ['dialog', 'tab'])
def test_translation_owner_is_destroyed_on_gui_thread_before_worker_gc(kind):
    result = run_probe(_OWNERSHIP, kind)
    assert result.returncode == 0, result.stdout + result.stderr


def test_registry_retains_children_and_retranslates_its_weak_self_entry():
    result = run_probe(_TRANSLATION, 'translation')
    assert result.returncode == 0, result.stdout + result.stderr
