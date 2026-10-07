"""Search, keyboard, responsive layout and theme/locale behavior on controlled widgets."""
import json
import os
import subprocess
import sys

import pytest


_SETUP = '''
import json
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QWidget
from je_auto_control.gui.tab_registry import TabSpec,TabRegistry
from je_auto_control.gui.workspace import WorkspaceShell
from je_auto_control.gui.theme import ThemeTokens,apply_theme
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
app=QApplication([]);called=[]
class Panel(QWidget):
    def menu_actions(self):
        return [('start',lambda:called.append('ran'))]
registry=TabRegistry([TabSpec('record','tab_record','core',Panel,default_visible=True),
                      TabSpec('mobile','tab_mobile','core',Panel),
                      TabSpec('diagnostics','tab_diagnostics','system',Panel)])
shell=WorkspaceShell(registry);shell.resize(1100,700);shell.show();app.processEvents()
'''


def _probe(body):
    pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
    result = subprocess.run([sys.executable, '-c', _SETUP + body], capture_output=True, text=True,
                            env=dict(os.environ, QT_QPA_PLATFORM='offscreen'), timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_search_reaches_all_features():
    report = _probe('''
registered_keys={spec.key for spec in registry.specs}
reachable_keys=set(shell.navigation.visible_keys())
assert reachable_keys==registered_keys
shell.navigation.search.setText('mobile');app.processEvents()
assert shell.navigation.visible_keys()==['mobile']
assert registry.instance('mobile') is None
shell.navigation.open_key('mobile');app.processEvents()
assert registry.instance('mobile') is shell.workspace.tabs.currentWidget()
shell.navigation.search.setText('no-such-feature');app.processEvents()
assert shell.navigation.visible_keys()==[] and shell.navigation.empty_state.isVisible()
shell.close();app.processEvents();print(json.dumps({'reachable':True}))
''')
    assert report['reachable'] is True


def test_keyboard_navigation_and_actions():
    report = _probe('''
QTest.keyClick(shell,Qt.Key.Key_K,Qt.KeyboardModifier.ControlModifier)
assert shell.navigation.search.hasFocus()
QTest.keyClicks(shell.navigation.search,'mobile')
QTest.keyClick(shell.navigation.search,Qt.Key.Key_Return);app.processEvents()
assert shell.workspace.tabs.currentWidget().property('tab_key')=='mobile'
focused_action=shell.workspace.current_tab_menu_actions()[0][1]
focused_action();assert called==['ran']
shell.close();app.processEvents();print(json.dumps({'keyboard':True}))
''')
    assert report['keyboard'] is True


def test_language_and_font_refresh():
    report = _probe('''
shell.navigation.search.setText('mobile');shell.navigation.open_key('mobile')
owner=registry.instance('mobile')
language_wrapper.reset_language('Traditional_Chinese');shell.retranslate()
assert shell.navigation.visible_keys()==['mobile']
assert registry.instance('mobile') is owner
assert shell.navigation.label_for_key('mobile')==language_wrapper.translate('tab_mobile')
apply_theme(shell,ThemeTokens.light(font_point_size=16));app.processEvents()
assert shell.font().pointSize()==16
assert ThemeTokens.light().palette.background in shell.styleSheet()
assert shell.navigation.visible_keys()==['mobile']
shell.close();app.processEvents();print(json.dumps({'refresh':True}))
''')
    assert report['refresh'] is True


def test_small_window_is_usable():
    report = _probe('''
shell.resize(640,480);app.processEvents()
assert shell.width()==640
assert not shell.details.isVisible()
assert shell.navigation.isVisible() and shell.workspace_scroll.isVisible()
assert shell.workspace_scroll.width()>=160
shell.navigation.open_key('mobile');app.processEvents()
assert registry.instance('mobile') is not None
shell.set_state('needs_permission','Controlled permission missing','Authorize the selected device.')
shell.toggle_details();app.processEvents()
assert shell.details.isVisible()
assert shell.details.state=='needs_permission'
assert 'Authorize the selected device.' in shell.details.reason.toPlainText()
shell.set_state('error','Controlled error','Retry explicitly.')
assert shell.details.state=='error'
shell.close();app.processEvents();print(json.dumps({'usable':True}))
''')
    assert report['usable'] is True


def test_full_catalog_and_main_window_keep_one_owner():
    report = _probe('''
from je_auto_control.gui.main_window import AutoControlGUIUI
window=AutoControlGUIUI();window.show();app.processEvents()
host=window.auto_control_gui_widget;chrome=window.workspace_shell
assert chrome.workspace is host and host.registry.owner is host
assert set(chrome.navigation.visible_keys())=={spec.key for spec in host.registry.specs}
assert len(chrome.navigation.visible_keys())==50
assert host.registry.instance('mobile') is None
assert host.registry.instance('screenshot') is None
chrome.navigation.search.setText('mobile');chrome.navigation.open_key('mobile');app.processEvents()
panel=host.registry.instance('mobile')
window._set_theme(True);window._apply_font_pt(16);app.processEvents()
assert chrome.font().pointSize()==16 and ThemeTokens.light().palette.background in chrome.styleSheet()
language_wrapper.reset_language('Japanese');app.processEvents()
assert chrome.navigation.visible_keys()==['mobile'] and host.registry.instance('mobile') is panel
assert chrome.navigation.label_for_key('mobile')==language_wrapper.translate('tab_mobile')
window.close();shell.close();app.processEvents();print(json.dumps({'integrated':True}))
''')
    assert report['integrated'] is True


def test_scroll_preserves_wide_content_and_reports_explicit_states():
    report = _probe('''
panel=registry.instance('record');panel.setMinimumWidth(1200)
shell.resize(640,480);app.processEvents()
assert shell.width()==640 and shell.workspace_scroll.horizontalScrollBar().maximum()>0
assert shell.workspace_scroll.widget() is shell.workspace and panel.width()>=1200
for state in ('empty','busy','error','needs_permission','needs_dependency','unsupported','ready'):
    shell.set_state(state,'Controlled reason','Controlled recovery',50 if state=='busy' else None)
    assert shell.details.state==state and 'Controlled recovery' in shell.details.reason.toPlainText()
shell.close();app.processEvents();print(json.dumps({'scroll':True}))
''')
    assert report['scroll'] is True


def test_theme_metadata_is_qt_free():
    result = subprocess.run([sys.executable, '-c', '''
import sys
from je_auto_control.gui.theme import ThemeTokens
assert ThemeTokens.dark().spacing==ThemeTokens.light().spacing
assert not any(name.startswith('PySide6') for name in sys.modules)
'''], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
