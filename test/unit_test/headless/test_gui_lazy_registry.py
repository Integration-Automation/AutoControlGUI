"""Lazy catalog ownership and compatible tab APIs without device input."""
import json
import os
import subprocess
import sys

import pytest


def _probe(code):
    pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
    result = subprocess.run([sys.executable, '-c', code], env=env, text=True,
                            capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_unopened_feature_is_not_imported():
    report = _probe('''
import json,sys
from PySide6.QtWidgets import QApplication
from je_auto_control.gui.main_widget import AutoControlGUIWidget
app=QApplication([])
widget=AutoControlGUIWidget()
unopened_module='je_auto_control.gui.mobile_tab'
assert unopened_module not in sys.modules
assert 'je_auto_control.gui._screenshot_tab' not in sys.modules
assert all(entry.widget is None for entry in widget._tab_entries if not entry.default_visible)
assert [entry['key'] for entry in widget.list_registered_tabs() if entry['visible']] == [
    'record','script_builder','remote_desktop']
widget.show_tab('mobile')
assert unopened_module in sys.modules
widget.close()
app.processEvents()
print(json.dumps({'lazy':True}))
''')
    assert report['lazy'] is True


def test_show_hide_list_api_compatible():
    report = _probe('''
import json
from PySide6.QtWidgets import QApplication
from je_auto_control.gui.main_widget import AutoControlGUIWidget
app=QApplication([]); widget=AutoControlGUIWidget()
before=widget.list_registered_tabs()
widget.show_tab('variables'); previous=widget._find_entry('variables').widget
widget.hide_tab('variables')
assert not next(row for row in widget.list_registered_tabs() if row['key']=='variables')['visible']
widget.show_tab('variables'); reopened=widget._find_entry('variables').widget
assert reopened is previous
assert reopened.property('tab_key') == 'variables'
assert widget.current_tab_menu_actions() == reopened.menu_actions()
widget.close_tab('variables'); app.processEvents()
widget.show_tab('variables')
assert widget._find_entry('variables').widget is not previous
assert [row['key'] for row in before] == [row['key'] for row in widget.list_registered_tabs()]
widget.show_tab('unknown'); widget.hide_tab('unknown')
widget.close();app.processEvents()
print(json.dumps({'compatible':True}))
''')
    assert report['compatible'] is True


def test_close_releases_subscriptions():
    report = _probe('''
import json
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication,QWidget
from je_auto_control.gui.tab_registry import TabSpec,TabRegistry
app=QApplication([]);listeners=set();owner=QWidget()
def factory():
    widget=QWidget();listeners.add(id(widget))
    ident=id(widget)
    widget.destroyed.connect(lambda: listeners.discard(ident))
    return widget
registry=TabRegistry([TabSpec('feature','title','system',factory)], parent=owner)
listeners_before_open=len(listeners)
previous=registry.open('feature')
previous_key=previous.property('tab_key')
assert registry.open('feature') is previous
registry.close('feature')
app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
assert len(listeners) == listeners_before_open
reopened=registry.open('feature')
assert reopened.property('tab_key') == previous_key == 'feature'
registry.close_all(); app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
assert len(listeners) == listeners_before_open
print(json.dumps({'released':True}))
''')
    assert report['released'] is True


def test_real_presence_listener_is_released_on_explicit_close():
    report = _probe('''
import json
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication
from je_auto_control.gui.main_widget import AutoControlGUIWidget
from je_auto_control.utils.remote_desktop.presence import default_presence_registry
app=QApplication([]);widget=AutoControlGUIWidget();registry=default_presence_registry()
before=len(registry._listeners)
widget.show_tab('presence')
assert len(registry._listeners)==before+1
widget.close_tab('presence')
app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
assert len(registry._listeners)==before
widget.close();app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
print(json.dumps({'released':True}))
''')
    assert report['released'] is True


def test_catalog_and_registry_metadata_do_not_import_qt_or_run_factories():
    result = subprocess.run([sys.executable, '-c', '''
import sys
from je_auto_control.gui.tab_registry import TabSpec,TabRegistry
from je_auto_control.gui._tab_catalog import TAB_CATALOG
def forbidden():
    raise AssertionError('metadata ran a widget factory')
registry=TabRegistry([TabSpec('feature','title','core',forbidden)])
assert registry.instance('feature') is None and len(registry.specs)==1
assert len(TAB_CATALOG)==50
assert not any(name.startswith('PySide6') for name in sys.modules)
'''], text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_registry_rejects_worker_thread_before_factory_or_widget_calls():
    report = _probe('''
import json
from threading import Thread
from PySide6.QtWidgets import QApplication,QWidget
from je_auto_control.gui.tab_registry import TabSpec,TabRegistry,TabRegistryError
app=QApplication([]);calls=[];failures=[]
def factory():
    calls.append('construct');return QWidget()
registry=TabRegistry([TabSpec('feature','title','core',factory)])
def attempt():
    try:registry.open('feature')
    except TabRegistryError:failures.append('thread rejected')
thread=Thread(target=attempt);thread.start();thread.join(2)
assert failures==['thread rejected'] and calls==[]
registry.open('feature');registry.close_all();app.processEvents()
print(json.dumps({'guarded':True}))
''')
    assert report['guarded'] is True


def test_closing_auto_click_stops_its_timer_before_widgets_are_deleted():
    report = _probe('''
import json
from PySide6.QtWidgets import QApplication
from je_auto_control.gui.main_widget import AutoControlGUIWidget
app=QApplication([]);widget=AutoControlGUIWidget()
widget.show_tab('auto_click');widget.timer.start(1000)
assert widget.timer.isActive()
widget.close_tab('auto_click')
assert not widget.timer.isActive()
widget.close();app.processEvents()
print(json.dumps({'stopped':True}))
''')
    assert report['stopped'] is True
