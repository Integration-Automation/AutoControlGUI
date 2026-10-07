"""Owned raw input cleanup, borrowed input isolation and retry without native input."""
import pytest


def test_cleanup_only_releases_owned_input():
    from je_auto_control.utils.executor.input_owner import InputOwner, _input_scope, _hold_input
    calls = []
    owner = InputOwner()
    with _input_scope(owner):
        _hold_input(('key', 1), lambda: False, lambda: calls.append('down1'), lambda: calls.append('up1'))
        _hold_input(('key', 2), lambda: True, lambda: calls.append('down2'), lambda: calls.append('up2'))
    owner.release_all()
    assert calls == ['down1', 'up1']


def test_unknown_state_refuses_allocation():
    from je_auto_control.utils.executor.input_owner import InputOwner, _input_scope, _hold_input
    calls = []
    with _input_scope(InputOwner()), pytest.raises(NotImplementedError):
        _hold_input(('key', 1), lambda: None, lambda: calls.append('down'), lambda: calls.append('up'))
    assert calls == []


def test_failed_release_retains_owned_input_for_retry():
    from je_auto_control.utils.executor.input_owner import InputOwner, _input_scope, _hold_input
    calls = []
    def release():
        calls.append('up')
        if len(calls) == 1:
            raise OSError('device unavailable')
    owner = InputOwner()
    with _input_scope(owner):
        _hold_input(('key', 1), lambda: False, lambda: None, release)
    with pytest.raises(OSError):
        owner.release_all()
    owner.release_all()
    assert calls == ['up', 'up']
