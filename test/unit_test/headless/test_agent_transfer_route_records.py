"""Coordinator route metadata has a separate finite quota and preserves consent tombstones on expiry."""
import importlib

import pytest

from headless.test_agent_transfer_records import make_records, record, activate
from je_auto_control.utils.agent_runtime import AgentTaskError


def test_only_128_durable_routes_can_be_retained(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    with records.store.connection(write=True) as connection:
        for number in range(128):
            records.reserve(connection, record(number, kind='route', account=None))
    with records.store.connection(write=True) as connection, pytest.raises(AgentTaskError, match='quota'):
        records.reserve(connection, record(129, kind='route', account=None))


def test_route_expiry_frees_only_its_metadata_and_keeps_key_revocation_fences(tmp_path, monkeypatch):
    records = make_records(tmp_path, monkeypatch)
    routed = record(1, kind='route', account=None, expires=1100.0, review_expires=1050.0)
    exported = record(2)
    activate(records, routed)
    activate(records, exported)
    monkeypatch.setattr(importlib.import_module(type(records).__module__).time, 'time', lambda: 1200.0)
    prune = getattr(records, 'prune_routes', None)
    assert callable(prune), 'expired route metadata requires an owned, writer-checked prune operation'
    with records.store.connection(write=True) as connection:
        assert prune(connection) == 1
        assert records.active(connection, exported['id'])['id'] == exported['id']
        assert connection.execute('SELECT count(*) FROM agent_transfer_routed_reviews').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM agent_transfer_revocations WHERE id=?',
                                  (routed['id'],)).fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM agent_transfer_intents WHERE review=?',
                                  (routed['review'],)).fetchone()[0] == 1
        with pytest.raises(AgentTaskError):
            records.reserve(connection, {**routed, 'created': 1200.0, 'expires': 1500.0, 'review_expires': 1300.0})
