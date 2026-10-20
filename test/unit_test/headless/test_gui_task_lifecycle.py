"""Shared GUI tasks preserve responsiveness, authority, cooperative cleanup and owner isolation."""
# ruff: noqa: E402  # reason: Qt must be guarded and configured before GUI imports
import asyncio
from concurrent.futures import CancelledError
from contextvars import ContextVar
import os
import gc
import threading
import time
import weakref

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QTimer, SIGNAL
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid

from je_auto_control.utils.exception.control_signals import OperationCancelledError
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.secret_scope import remember_secret, secret_log_scope
from je_auto_control.utils.rbac.authorization import (
    AuthorizationContext, authorization_scope, current_authorization, resolve_token,
)
from je_auto_control.utils.rbac.policy import authorize_command
from je_auto_control.utils.rbac.users import Role, UserStore


def _pump(app, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.001)
    return predicate()


@pytest.fixture
def tasks():
    from je_auto_control.gui.task_controller import TaskController
    app = QApplication.instance() or QApplication([])
    controller, owner = TaskController(), QWidget()
    try:
        yield app, controller, owner
    finally:
        if isValid(controller):
            controller.close()
        assert _pump(app, lambda: controller.active_count == 0)
        if isValid(owner):
            owner.deleteLater()
        if isValid(controller):
            controller.deleteLater()


def test_ui_tick_continues_during_network_wait(tasks):
    app, controller, owner = tasks
    entered, release = threading.Event(), threading.Event()
    results, ticks = [], []

    def work(_token):
        entered.set()
        assert release.wait(3)
        return threading.get_ident()

    handle = controller.submit(work, owner=owner)
    handle.finished.connect(lambda result: results.append((result, threading.get_ident())))
    try:
        assert entered.wait(1)
        QTimer.singleShot(0, lambda: ticks.append('tick'))
        assert _pump(app, lambda: ticks)
        assert not results and handle.is_running
    finally:
        release.set()
    assert _pump(app, lambda: results and controller.active_count == 0)
    outcome, callback_thread = results[0]
    assert outcome.status == 'ok' and outcome.task_id == handle.task_id
    assert outcome.value != threading.get_ident() and callback_thread == threading.get_ident()


def test_cancel_releases_session(tasks):
    app, controller, owner = tasks
    entered, released = threading.Event(), threading.Event()
    sessions = []

    def work(token):
        sessions.append('session')
        entered.set()
        try:
            token.wait(3)
            token.checkpoint()
        finally:
            sessions.clear()
            released.set()

    handle = controller.submit(work, owner=owner)
    assert entered.wait(1)
    handle.cancel()
    assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    assert handle.outcome.status == 'cancelled'
    assert released.is_set() and sessions == [] and not handle.is_running


def test_owner_death_drops_result(tasks):
    app, controller, owner = tasks
    entered, release = threading.Event(), threading.Event()
    received = []

    def ignores_cancel(_token):
        entered.set()
        assert release.wait(3)
        return 'late data'

    handle = controller.submit(ignores_cancel, owner=owner)
    handle.finished.connect(received.append)
    try:
        assert entered.wait(1)
        owner.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    finally:
        release.set()
    assert _pump(app, lambda: controller.active_count == 0)
    assert received == [] and handle.outcome is None and handle.is_cancelled


def test_no_worker_touches_widget(tasks):
    app, controller, owner = tasks
    release = threading.Event()
    progress_threads, progress = [], []

    def work(token):
        assert release.wait(3)
        token.report(1, 2, 'controlled')
        return 'inert data'

    handle = controller.submit(work, owner=owner)
    handle.progress.connect(lambda value: (progress.append(value), progress_threads.append(threading.get_ident())))
    release.set()
    assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    assert progress_threads == [threading.get_ident()]
    assert (progress[0].completed, progress[0].total, progress[0].detail) == (1, 2, 'controlled')
    assert progress[0].task_id == handle.task_id


def test_submission_captures_context_and_viewer_authority_without_drive_privilege(tasks):
    app, controller, owner = tasks
    marker = ContextVar('task-lifecycle-marker', default='ambient')
    marker_token = marker.set('registrant')
    try:
        with authorization_scope(AuthorizationContext('reader', 'viewer')):
            handle = controller.submit(lambda _token: (marker.get(), current_authorization()), owner=owner)
    finally:
        marker.reset(marker_token)
    assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    assert handle.outcome.status == 'ok'
    value, authority = handle.outcome.value
    assert value == 'registrant' and authority.user_id == 'reader' and authority.role == 'viewer'
    assert current_authorization() is None and marker.get() == 'ambient'


@pytest.mark.parametrize('kind', ['keyboard', 'exit', 'generator', 'async', 'future', 'operation'])
@pytest.mark.parametrize('wrapped', [False, True])
def test_direct_and_wrapped_controls_have_a_cancelled_outcome_instead_of_an_ordinary_error(tasks, kind, wrapped):
    app, controller, owner = tasks

    def work(_token):
        original = {'keyboard': KeyboardInterrupt(), 'exit': SystemExit(7), 'generator': GeneratorExit(),
                    'async': asyncio.CancelledError(), 'future': CancelledError(),
                    'operation': OperationCancelledError('task')}[kind]
        if wrapped:
            raise RuntimeError('provider wrapper') from original
        raise original

    handle = controller.submit(work, owner=owner)
    assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    assert handle.outcome.status == 'cancelled' and handle.outcome.error == ''


def test_an_ordinary_error_finishes_once_and_does_not_block_a_later_task(tasks):
    app, controller, owner = tasks
    outcomes = []

    def broken(_token):
        raise ValueError('controlled failure')

    handle = controller.submit(broken, owner=owner)
    handle.finished.connect(outcomes.append)
    assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    assert handle.outcome.status == 'error' and 'controlled failure' in handle.outcome.error
    assert len(outcomes) == 1
    later = controller.submit(lambda _token: 42, owner=owner)
    assert _pump(app, lambda: later.outcome is not None and controller.active_count == 0)
    assert later.outcome.status == 'ok' and later.outcome.value == 42 and later.task_id != handle.task_id


def test_start_failure_does_not_leak_worker_or_controller_job(tasks, monkeypatch):
    from je_auto_control.gui import _worker_thread
    _app, controller, owner = tasks
    previous = set(_worker_thread._RUNNING)
    original = RuntimeError('controlled thread start failure')

    def failed_start(_thread):
        raise original

    monkeypatch.setattr(threading.Thread, 'start', failed_start)
    try:
        with pytest.raises(RuntimeError) as caught:
            controller.submit(lambda _token: None, owner=owner)
        assert caught.value is original
        assert controller.active_count == 0 and set(_worker_thread._RUNNING) == previous
    finally:
        # A failed pre-fix run must not leave an unstarted thread for atexit to join.
        for handle in set(_worker_thread._RUNNING)-previous:
            _worker_thread._RUNNING.pop(handle).deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        original.__traceback__ = None
        del caught


@pytest.mark.parametrize('change', ['remove', 'demote', 'corrupt'])
def test_authority_is_refreshed_before_work_not_merely_copied_at_submission(tasks, tmp_path, monkeypatch, change):
    from je_auto_control.gui import task_controller
    app, controller, owner = tasks
    entered, release = threading.Event(), threading.Event()
    run = task_controller._TaskWorker.run
    calls = []

    def held_run(worker):
        entered.set()
        assert release.wait(3)
        run(worker)

    def work(_token):
        authorize_command('AC_history_capture')
        calls.append('authorized')

    monkeypatch.setattr(task_controller._TaskWorker, 'run', held_run)
    store = UserStore(tmp_path/'users.json')
    token = store.add_user(user_id='registrant', display_name='Registrant', role=Role.ADMIN)
    context = resolve_token(store, token)
    with authorization_scope(context):
        handle = controller.submit(work, owner=owner)
    try:
        assert entered.wait(1)
        other = UserStore(store.path)
        if change == 'remove':
            other.remove_user('registrant')
        elif change == 'demote':
            other.set_role('registrant', Role.VIEWER)
        else:
            store.path.write_text('corrupted', encoding='utf-8')
    finally:
        release.set()
    assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    assert handle.outcome.status == 'error' and calls == []


def test_destroying_one_owner_does_not_cancel_another_owners_work(tasks):
    app, controller, first_owner = tasks
    second_owner = QWidget()
    first_entered, second_entered, release = threading.Event(), threading.Event(), threading.Event()

    def first_work(token):
        first_entered.set()
        token.wait(3)
        token.checkpoint()

    def second_work(_token):
        second_entered.set()
        assert release.wait(3)
        return 'second owner'

    first = controller.submit(first_work, owner=first_owner)
    second = controller.submit(second_work, owner=second_owner)
    try:
        assert first_entered.wait(1) and second_entered.wait(1)
        first_owner.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert first.is_cancelled and not second.is_cancelled
    finally:
        release.set()
    assert _pump(app, lambda: second.outcome is not None and controller.active_count == 0)
    assert first.outcome is None and second.outcome.value == 'second owner'
    second_owner.deleteLater()


def test_destroying_controller_cancels_jobs_and_drops_late_results(tasks):
    app, controller, owner = tasks
    entered = threading.Event()
    outcomes = []

    def work(token):
        entered.set()
        token.wait(3)
        token.checkpoint()

    handle = controller.submit(work, owner=owner)
    handle.finished.connect(outcomes.append)
    assert entered.wait(1)
    controller.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert _pump(app, lambda: controller.active_count == 0)
    assert handle.is_cancelled and handle.outcome is None and outcomes == []


def test_discarding_a_handle_does_not_retain_it_through_worker_callbacks(tasks):
    app, controller, owner = tasks
    entered = threading.Event()

    def work(token):
        entered.set()
        token.wait(3)
        token.checkpoint()

    handle = controller.submit(work, owner=owner)
    handle_ref = weakref.ref(handle)
    assert entered.wait(1)
    del handle
    gc.collect()
    assert handle_ref() is None
    assert _pump(app, lambda: controller.active_count == 0)


def test_worker_and_handle_do_not_keep_the_owner_alive_through_a_callback_cycle(tasks):
    app, controller, _owner = tasks
    owner = QWidget()
    owner_ref = weakref.ref(owner)
    entered = threading.Event()

    def work(token):
        entered.set()
        token.wait(3)
        token.checkpoint()

    handle = controller.submit(work, owner=owner)
    assert entered.wait(1)
    del owner
    gc.collect()
    assert owner_ref() is None
    assert _pump(app, lambda: controller.active_count == 0)
    assert handle.outcome is None and handle.is_cancelled


def test_foreign_and_late_progress_or_results_cannot_replace_this_tasks_outcome(tasks):
    from je_auto_control.gui.task_controller import TaskOutcome, TaskProgress
    app, controller, owner = tasks
    release = threading.Event()
    progress = []

    def work(_token):
        assert release.wait(3)
        return 'correct'

    handle = controller.submit(work, owner=owner)
    handle.progress.connect(progress.append)
    try:
        handle.complete(TaskOutcome(handle.task_id+1, 'ok', 'foreign'))
        handle.forward_progress(TaskProgress(handle.task_id+1, 1))
        assert handle.outcome is None and progress == []
    finally:
        release.set()
    assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    handle.complete(TaskOutcome(handle.task_id, 'error', error='late'))
    handle.forward_progress(TaskProgress(handle.task_id, 2))
    assert handle.outcome.value == 'correct' and progress == []


def test_late_cooperative_stop_does_not_relabel_successful_committed_work(tasks):
    app, controller, owner = tasks
    entered = threading.Event()

    def work(token):
        entered.set()
        token.wait(3)
        return 'committed'

    handle = controller.submit(work, owner=owner)
    assert entered.wait(1)
    handle.cancel()
    assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    assert handle.is_cancelled and handle.outcome.status == 'ok' and handle.outcome.value == 'committed'


@pytest.mark.parametrize('operation', ['submit', 'close'])
def test_lifecycle_mutations_are_rejected_off_the_gui_thread(tasks, operation):
    _app, controller, owner = tasks
    errors = []

    def off_thread():
        try:
            if operation == 'submit':
                controller.submit(lambda _token: None, owner=owner)
            else:
                controller.close()
        except AutoControlException as error:
            errors.append(str(error))

    thread = threading.Thread(target=off_thread)
    thread.start()
    thread.join(1)
    assert not thread.is_alive() and len(errors) == 1 and controller.active_count == 0


def test_failure_cause_tracebacks_are_released_before_outcome_delivery(tasks):
    app, controller, owner = tasks
    original, wrapper = ValueError('controlled'), RuntimeError('wrapped')

    def work(_token):
        try:
            raise original
        except ValueError:
            raise wrapper from original

    handle = controller.submit(work, owner=owner)
    assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    assert handle.outcome.status == 'error'
    assert original.__traceback__ is None and wrapper.__traceback__ is None


def test_worker_progress_and_error_text_use_the_captured_secret_scope(tasks):
    app, controller, owner = tasks
    release = threading.Event()
    progress = []
    secret = 'controlled-mask-value-92374'

    def work(token):
        assert release.wait(3)
        token.report(1, 2, 'progress '+secret)
        raise ValueError('error '+secret)

    with secret_log_scope():
        remember_secret(secret)
        handle = controller.submit(work, owner=owner)
        handle.progress.connect(progress.append)
        release.set()
        assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    assert len(progress) == 1 and secret not in progress[0].detail and '***' in progress[0].detail
    assert handle.outcome.status == 'error' and secret not in handle.outcome.error and '***' in handle.outcome.error


@pytest.mark.parametrize('kind', ['ordinary', 'keyboard', 'exit', 'generator', 'async', 'future', 'operation'])
def test_broken_error_formatters_still_deliver_one_typed_terminal_outcome(tasks, kind):
    app, controller, owner = tasks

    class BrokenDetail(ValueError):
        def __repr__(self):
            controls = {'ordinary': ValueError('broken formatter'), 'keyboard': KeyboardInterrupt(),
                        'exit': SystemExit(7), 'generator': GeneratorExit(), 'async': asyncio.CancelledError(),
                        'future': CancelledError(), 'operation': OperationCancelledError('formatter')}
            raise controls[kind]

    def work(_token):
        raise BrokenDetail('controlled')

    handle = controller.submit(work, owner=owner)
    assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    if kind == 'ordinary':
        assert handle.outcome.status == 'error' and 'detail unavailable' in handle.outcome.error
    else:
        assert handle.outcome.status == 'cancelled' and handle.outcome.error == ''


def test_retiring_tasks_disconnects_owner_notifications_instead_of_accumulating_them(tasks):
    app, controller, owner = tasks
    primer = owner.destroyed.connect(lambda: None)
    QObject.disconnect(primer)  # prime PySide's one-time signal bookkeeping before measuring
    initial = owner.receivers(SIGNAL('destroyed(QObject*)'))
    for _ in range(10):
        handle = controller.submit(lambda _token: 'controlled', owner=owner)
        assert _pump(app, lambda: handle.outcome is not None and controller.active_count == 0)
    assert owner.receivers(SIGNAL('destroyed(QObject*)')) == initial
