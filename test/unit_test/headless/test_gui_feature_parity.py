"""Full catalog/default workflow, synthetic mixed DPI and fresh-process Qt-free imports."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def _probe(body):
    pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
    result = subprocess.run([sys.executable, '-c', body], capture_output=True, text=True, timeout=90,
                            env=dict(os.environ, QT_QPA_PLATFORM='offscreen'))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_default_workflow_and_full_catalog():
    report = _probe('''
import json
from PySide6.QtWidgets import QApplication
from je_auto_control.gui.main_widget import AutoControlGUIWidget
from benchmarks.gui_workloads import catalog_report,recovery_report
app=QApplication([]);widget=AutoControlGUIWidget()
report=catalog_report(widget)
assert report['default_keys']==['record','script_builder','remote_desktop']
assert len(report['registered_keys'])==50
for key in report['registered_keys']:
    widget.show_tab(key)
    assert widget.tabs.currentWidget().property('tab_key')==key
from je_auto_control.gui._dependency_panel import DependencyPanel
missing=DependencyPanel('controlled unavailable backend')
assert recovery_report(missing.property('capability_reason'))['unsupported_feature_has_reason']
widget.close();app.processEvents();print(json.dumps(report))
''')
    assert len(set(report['registered_keys'])) == 50


def test_mixed_dpi_geometry():
    report = _probe('''
import json
from types import SimpleNamespace
from PySide6.QtCore import QRect
from je_auto_control.gui import _screen_geometry as geometry
geometry.sys=SimpleNamespace(platform='win32')
screens=[SimpleNamespace(geometry=lambda:QRect(-1920,0,1920,1080),devicePixelRatio=lambda:1),
         SimpleNamespace(geometry=lambda:QRect(0,-164,1536,864),devicePixelRatio=lambda:1.25),
         SimpleNamespace(geometry=lambda:QRect(1920,0,960,540),devicePixelRatio=lambda:2)]
for screen in screens:
    native=geometry.native_region(screen,QRect(40,80,200,100))
    logical=geometry.logical_point(screen,*native[:2])
    origin=screen.geometry().topLeft()
    assert logical.x()==origin.x()+40 and logical.y()==origin.y()+80
geometry.sys=SimpleNamespace(platform='darwin')
assert geometry.native_region(screens[-1],QRect(40,80,200,100))==(1960,80,200,100)
print(json.dumps({'synthetic_mixed_dpi':True,'native_monitors':False}))
''')
    assert report['synthetic_mixed_dpi'] is True


def test_import_facade_is_qt_free():
    completed = subprocess.run([sys.executable, '-c', '''
import sys,je_auto_control
from benchmarks.gui_workloads import waiting_script
assert waiting_script(.1)
assert not any(name.startswith(('PySide6','shiboken6')) for name in sys.modules)
'''], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr


def test_benchmark_refuses_mismatched_environment():
    from benchmarks.gui_startup import compare_reports
    before = {'environment': {'python': '3.14', 'qt': 'offscreen'}, 'workload': 'same',
              'runs': [{'startup_ms': 10, 'memory': 100, 'first_open_ms': 1, 'event_loop_p95_ms': 20}]}
    after = dict(before, environment={'python': '3.10', 'qt': 'offscreen'})
    with pytest.raises(ValueError, match='environment'):
        compare_reports(before, after)


def test_calibrated_budget_rejects_a_blocked_event_loop():
    from benchmarks.gui_startup import check_budgets
    root = Path(__file__).resolve().parents[3]
    folder = root / 'benchmarks/results/gui-workspace-f4'
    before = json.loads((folder / 'before.json').read_text(encoding='utf-8'))
    after = json.loads((folder / 'after.json').read_text(encoding='utf-8'))
    budget = json.loads((folder / 'budgets.json').read_text(encoding='utf-8'))
    assert check_budgets(before, after, budget)['passed']
    for run in after['runs']:
        run['event_loop_p95_ms'] = 100
    result = check_budgets(before, after, budget)
    assert not result['passed']
    assert not result['budget_checks']['event_loop_p95_ms']['passed']
