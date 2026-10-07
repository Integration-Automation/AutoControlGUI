"""Cross-layer acceptance preserves provenance, persisted state and honest evidence."""
import json
import runpy
from pathlib import Path

import pytest


@pytest.fixture
def verifier():
    return runpy.run_path(str(Path(__file__).resolve().parents[2] / 'verify/modernization_verify.py'))


def test_journal_to_script_to_device_result(tmp_path, verifier):
    report = verifier['journal_round_trip'](tmp_path)
    assert report['source_steps'] == report['replayed_steps']
    assert report['device_results'] == [[12, 24]]
    assert report['mode'] == 'controlled'


def test_sync_restart_and_gui_session(tmp_path, monkeypatch, verifier):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.config_sync_tab import ConfigSyncTab
    app = QApplication.instance() or QApplication([])
    report = verifier['sync_restart'](tmp_path)
    panel = ConfigSyncTab()
    try:
        panel._done(report)
        displayed = json.loads(panel.results.toPlainText())
        assert displayed['revision'] == report['committed_revision'] == report['reopened_revision']
        assert panel._worker is None
    finally:
        panel.close()
        panel.deleteLater()
        app.processEvents()


def test_platform_capability_report_has_evidence(tmp_path, verifier):
    report = verifier['acceptance_report'](tmp_path)
    verifier['validate_report'](report)
    assert all(row['evidence'] and row['actual'] for row in report['checks'] if row['status'] == 'verified')
    assert all(row['reason'] for row in report['checks'] if row['status'] == 'skipped')
    assert report['platform'] and report['backend'] and report['versions']['python']
    dishonest = dict(report, checks=[dict(report['checks'][0], evidence=[])])
    with pytest.raises(ValueError, match='evidence'):
        verifier['validate_report'](dishonest)
    dishonest['checks'][0]['evidence'] = [str(tmp_path / 'nonexistent') ]
    with pytest.raises(ValueError, match='evidence'):
        verifier['validate_report'](dishonest)


def test_macos_report_preserves_failed_native_probe(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / 'verify/macos_verify.py'
    module = runpy.run_path(str(path))
    scope = module['main'].__globals__
    outcome = module['Outcome']
    monkeypatch.setitem(scope, 'PROBES', [('available', lambda: outcome(True, 'actual result')),
                                         ('denied', lambda: outcome(False, 'permission denied'))])
    monkeypatch.setitem(scope, 'EXPECTED', {'available': True, 'denied': True})
    output = tmp_path / 'macos.json'
    assert module['main'](['--output', str(output)]) == 1
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['checks'][0]['status'] == 'verified'
    assert report['checks'][1]['status'] == 'failed'
    assert report['checks'][1]['actual'] is False
    assert report['checks'][1]['evidence'] == ['permission denied']
