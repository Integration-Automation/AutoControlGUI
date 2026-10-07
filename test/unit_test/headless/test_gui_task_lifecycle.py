"""Controlled cancellation, deadline, delivery and ownership regressions for GUI tasks."""
import os
import subprocess
import sys

import pytest


_SETUP = '''
import threading,time
from PySide6.QtCore import QCoreApplication,QEvent,QTimer
from PySide6.QtWidgets import QApplication,QWidget
from je_auto_control.gui.task_controller import TaskController,TaskResult,TaskProgress
app=QApplication([]);owner=QWidget();owner.show();controller=TaskController(timeout_s=2)
def pump(predicate,timeout=3):
    end=time.monotonic()+timeout
    while not predicate() and time.monotonic()<end:
        app.processEvents();time.sleep(.005)
    app.processEvents();assert predicate()
'''


def _probe(body):
    pytest.importorskip('PySide6.QtWidgets', exc_type=ImportError)
    completed = subprocess.run([sys.executable, '-c', _SETUP + body], capture_output=True, text=True,
                               env=dict(os.environ, QT_QPA_PLATFORM='offscreen'), timeout=30)
    assert completed.returncode == 0, completed.stderr


def test_ui_tick_continues_during_network_wait():
    _probe('''
ticks=[];release=threading.Event();started=threading.Event()
timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(1));timer.start()
def work(token):
    started.set();release.wait(.15);token.checkpoint();return 'network reply'
handle=controller.submit(work,owner=owner)
pump(lambda:len(ticks)>4 and started.is_set());ui_ticks_during_work=len(ticks)
assert ui_ticks_during_work>0
release.set();pump(lambda:handle.result is not None)
assert isinstance(handle.result,TaskResult) and handle.result.value=='network reply'
''')


def test_cancel_raw_input_releases_owned_key_and_preserves_borrowed_shift():
    _probe('''
from je_auto_control.wrapper import auto_control_keyboard as keys
events=[];started=threading.Event();released=threading.Event()
shift=keys._resolve_keycode('shift');key=keys._resolve_keycode('a')
keys.keyboard_check.check_key_is_press=lambda code:code==shift
keys.keyboard.press_key=lambda code:events.append(('down',code))
def release(code):
    events.append(('up',code));released.set()
keys.keyboard.release_key=release
def work(token):
    keys.press_keyboard_key('a',is_shift=True,skip_record=True)
    started.set();token.wait(30)
handle=controller.submit(work,owner=owner);pump(started.is_set);handle.cancel()
pump(released.is_set);pump(lambda:not handle.is_running)
assert events==[('down',key),('up',key)]
''')


def test_successful_raw_hold_is_released_when_its_panel_is_destroyed():
    _probe('''
from je_auto_control.wrapper import auto_control_keyboard as keys
events=[];released=threading.Event();key=keys._resolve_keycode('a')
keys.keyboard_check.check_key_is_press=lambda code:False
keys.keyboard.press_key=lambda code:events.append(('down',code))
def release(code):
    events.append(('up',code));released.set()
keys.keyboard.release_key=release
handle=controller.submit(lambda token:keys.press_keyboard_key('a',skip_record=True),owner=owner)
pump(lambda:handle.result is not None)
assert events==[('down',key)]
owner.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
pump(released.is_set)
assert events==[('down',key),('up',key)]
''')


def test_window_listing_and_hud_sampling_are_off_gui_thread():
    _probe('''
from je_auto_control.gui import window_tab,live_hud_tab
threads=[];gui=threading.get_ident()
window_tab.list_windows=lambda:threads.append(threading.get_ident()) or [(123,'Controlled')]
windows=window_tab.WindowManagerTab()
pump(lambda:windows._table.rowCount()==1)
assert threads==[threads[0]] and threads[0]!=gui
hud=live_hud_tab.LiveHUDTab();release=threading.Event();started=threading.Event()
def sample():
    threads.append(threading.get_ident());started.set();release.wait(1);return (4,5)
hud._mouse.sample=sample;hud._pixel.sample=lambda x,y:(1,2,3)
hud._tick();pump(started.is_set)
for _ in range(10):hud._tick()
assert len(threads)==2 and threads[-1]!=gui
release.set();pump(lambda: '(4, 5)' in hud._pos_label.text())
windows.deleteLater();hud.deleteLater()
QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
''')


def test_secret_metadata_is_read_on_worker_without_locking_gui():
    _probe('''
from je_auto_control.gui import secrets_tab
threads=[];gui=threading.get_ident()
class Manager:
    @property
    def is_initialized(self):
        threads.append(threading.get_ident());return True
    @property
    def is_unlocked(self):
        threads.append(threading.get_ident());return True
    def list_names(self):
        threads.append(threading.get_ident());return ['example']
secrets_tab.default_secret_manager=Manager()
tab=secrets_tab.SecretsTab()
pump(lambda:tab._list.count()==1)
assert threads and all(thread!=gui for thread in threads)
tab.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
''')


def test_legacy_worker_owner_death_wakes_nested_sleep_and_releases_raw_hold():
    _probe('''
from je_auto_control.gui._worker_thread import CallWorker,start_worker,running_threads
from je_auto_control.wrapper import auto_control_keyboard as keys
from je_auto_control.utils.executor.action_executor import execute_action
events=[];started=threading.Event();released=threading.Event();values=[]
key=keys._resolve_keycode('a')
keys.keyboard_check.check_key_is_press=lambda code:False
keys.keyboard.press_key=lambda code:events.append(('down',code))
def release(code):
    events.append(('up',code));released.set()
keys.keyboard.release_key=release
def work():
    keys.press_keyboard_key('a',skip_record=True);started.set()
    execute_action([['AC_sleep',{'seconds':30}]]);return 'late'
job=start_worker(owner,CallWorker(work),on_done=values.append,on_thread_done=lambda:None)
pump(started.is_set);assert job.isRunning();owner.deleteLater()
QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
pump(released.is_set);pump(lambda:not job.isRunning())
assert values==[] and events==[('down',key),('up',key)]
''')


def test_global_service_stop_waits_off_qt_and_keeps_ui_ticks_running():
    _probe('''
from je_auto_control.gui import rest_api_tab
ticks=[];started=threading.Event();release=threading.Event();threads=[];gui=threading.get_ident()
class Registry:
    def status(self):return {'running':False,'url':'','token':''}
    def stop(self):
        threads.append(threading.get_ident());started.set();release.wait(1)
rest_api_tab.rest_api_registry=Registry()
tab=rest_api_tab.RestApiTab()
timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(1));timer.start()
tab._on_stop();pump(lambda:started.is_set() and len(ticks)>3)
assert threads==[threads[0]] and threads[0]!=gui
release.set();pump(lambda:tab._service_tasks.handle is None)
tab.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
''')


def test_cancel_releases_session():
    _probe('''
sessions=[];started=threading.Event();released=threading.Event()
def work(token):
    sessions.append('owned');started.set()
    try:
        token.event.wait(1);token.checkpoint()
    finally:
        sessions.clear();released.set()
handle=controller.submit(work,owner=owner)
pump(started.is_set);handle.cancel();pump(released.is_set);pump(lambda:not handle.is_running)
active_sessions_after_close=len(sessions)
assert active_sessions_after_close==0 and handle.result is None
assert handle.state=='cancelled'
''')


def test_owner_death_drops_result():
    _probe('''
release=threading.Event();started=threading.Event();done=threading.Event();values=[]
def work(token):
    started.set();release.wait(1);done.set();return 'obsolete'
handle=controller.submit(work,owner=owner);handle.completed.connect(values.append)
pump(started.is_set);owner.deleteLater()
QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
release.set();pump(done.is_set)
result_after_owner_death=handle.result
assert result_after_owner_death is None and values==[] and handle.token.event.is_set()
''')


def test_no_worker_touches_widget():
    _probe('''
gui_thread=threading.get_ident();threads=[];progress=[]
def work(token):
    threads.append(threading.get_ident());token.report(50,'controlled progress');return 123
handle=controller.submit(work,owner=owner)
handle.progress.connect(lambda value:progress.append((threading.get_ident(),value)))
pump(lambda:handle.result is not None)
assert threads!=[gui_thread] and isinstance(handle.result,TaskResult)
assert progress and progress[0][0]==gui_thread and isinstance(progress[0][1],TaskProgress)
assert owner.property('execution_state')=='ready'
''')


def test_superseded_run_and_deadline_drop_obsolete_delivery():
    _probe('''
release=threading.Event();started=threading.Event();old_done=threading.Event();values=[]
def old_work(token):
    started.set();release.wait(1);old_done.set();return 'old'
old=controller.submit(old_work,owner=owner);old.completed.connect(values.append)
pump(started.is_set)
new=controller.submit(lambda token:'new',owner=owner);pump(lambda:new.result is not None)
release.set();pump(old_done.is_set);app.processEvents()
assert values==[] and old.result is None and new.result.value=='new'
short=TaskController(timeout_s=.05)
def waiting(token):
    token.event.wait(1);token.checkpoint();return 'late'
timed=short.submit(waiting,owner=owner);pump(lambda:not timed.is_running)
assert timed.state=='timed_out' and timed.result is None
''')


def test_record_panel_close_stops_its_owned_hook():
    _probe('''
from queue import Queue
import je_auto_control.wrapper._record_panel_owner as native
from je_auto_control.gui.main_widget import AutoControlGUIWidget
owned=[];stopped=[];borrowed={'running':True,'stops':0}
import je_auto_control.gui._record_tab as legacy
def borrowed_start():
    borrowed['starts']=borrowed.get('starts',0)+1;return True
def borrowed_stop():
    borrowed['stops']+=1;borrowed['running']=False;return []
legacy.record=borrowed_start;legacy.stop_record=borrowed_stop
class FakeRecorder:
    def record(self):owned.append(self)
    def stop_record(self):
        stopped.append(self);owned.remove(self);return Queue()
native._new_recorder=FakeRecorder
host=AutoControlGUIWidget();host._start_record()
pump(lambda:bool(owned) and host._record_job is None)
instance=owned[0];host.close_tab('record');pump(lambda:not owned)
assert stopped==[instance] and borrowed=={'running':True,'stops':0}
host.show_tab('record');assert host.registry.instance('record') is not None
assert not owned
host.close();app.processEvents()
''')


def test_record_cleanup_retains_failure_for_retry():
    from queue import Queue
    import time
    from je_auto_control.wrapper._record_panel_owner import RecordPanelOwner, _RETIRED

    class FakeRecorder:
        stops = 0

        def record(self):
            pass

        def stop_record(self):
            self.stops += 1
            if self.stops == 1:
                raise OSError('controlled native cleanup failure')
            return Queue()

    native = FakeRecorder()
    owner = RecordPanelOwner(lambda: native)
    owner.start()
    owner.request_close()
    deadline = time.monotonic() + 3
    while owner.cleanup_running and time.monotonic() < deadline:
        time.sleep(.005)
    assert owner in _RETIRED and owner.cleanup_error == 'controlled native cleanup failure'
    owner.request_close()
    deadline = time.monotonic() + 3
    while owner.cleanup_running and time.monotonic() < deadline:
        time.sleep(.005)
    assert owner not in _RETIRED and native.stops == 2 and owner.cleanup_error == ''


def test_executor_checks_cancellation_between_nested_actions():
    _probe('''
from je_auto_control.utils.executor.action_executor import Executor
started=threading.Event();release=threading.Event();actions=[]
def work(token):
    runner=Executor()
    def blocked():
        actions.append('first');started.set();release.wait(1)
    runner.event_dict['AC_test_blocked']=blocked
    runner.event_dict['AC_test_late']=lambda:actions.append('late')
    return runner.execute_action([['AC_test_blocked'],['AC_test_late']],raise_on_error=True)
handle=controller.submit(work,owner=owner);pump(started.is_set)
handle.cancel();release.set();pump(lambda:not handle.is_running)
assert actions==['first'] and handle.result is None
''')


def test_webrtc_offer_generation_runs_off_gui_thread():
    _probe('''
from PySide6.QtWidgets import QLabel,QPlainTextEdit
from je_auto_control.gui.remote_desktop.webrtc_host_session import WebRTCHostSessionController
threads=[];created=threading.Event()
class Host:
    def create_session_offer(self):
        threads.append(threading.get_ident());time.sleep(.1);created.set();return 'peer','controlled sdp'
    def stop_session(self,identifier):pass
class Sessions:
    owner='controlled-owner'
    def __init__(self):
        from je_auto_control.utils.remote_desktop.registry import _RemoteDesktopRegistry
        self.directory=_RemoteDesktopRegistry()
        self.session=self.directory.reserve_session(owner=self.owner,transport='webrtc',role='host')
    def id(self,role):return self.session.id
panel=QWidget();panel._multi_host=Host();panel._sessions=Sessions()
panel._offer_view=QPlainTextEdit();panel._status_label=QLabel();panel._manual_session_id=None
panel._require_multi_host=lambda:panel._multi_host
panel._show_error=lambda failure:None
native=WebRTCHostSessionController(panel);native._produce_offer()
pump(lambda:panel._offer_view.toPlainText()=='controlled sdp')
assert threads and threads[0]!=threading.get_ident() and panel._manual_session_id=='peer'
''')


def test_revoked_webrtc_answer_does_not_write_a_new_pin():
    from je_auto_control.gui._task_state import CancellationToken, TaskCancelled
    from je_auto_control.gui.remote_desktop._task_work import AnswerRequest, SignalingTarget, create_answer
    import threading

    revoked = threading.Event()
    closed = threading.Event()
    pins = []

    class Viewer:
        def process_offer(self, offer, expected_dtls_fingerprint=None):
            revoked.set()
            return 'answer'

    class Pins:
        def dtls_fingerprint_for(self, identifier):
            return None

        def remember_dtls_fingerprint(self, identifier, fingerprint):
            pins.append((identifier, fingerprint))

    request = AnswerRequest(Viewer(), 'owned', 'a=fingerprint:sha-256 00:11', closed.set,
                            SignalingTarget('original-server', 'original-host', None), Pins(),
                            lambda: not revoked.is_set())
    with pytest.raises(TaskCancelled):
        create_answer(request, CancellationToken('run', 2, lambda value: None))
    assert closed.wait(2) and pins == []


def test_revoked_webrtc_offer_releases_only_the_allocated_peer():
    from je_auto_control.gui._task_state import CancellationToken, TaskCancelled
    from je_auto_control.gui.remote_desktop._task_work import create_offer
    import threading

    revoked = threading.Event()
    closed = threading.Event()
    stopped = []

    class Host:
        def create_session_offer(self):
            revoked.set()
            return 'owned-peer', 'sdp'

        def stop_session(self, identifier):
            stopped.append(identifier)
            closed.set()

    with pytest.raises(TaskCancelled):
        create_offer(Host(), 'owned', lambda: not revoked.is_set(),
                     CancellationToken('run', 2, lambda value: None))
    assert closed.wait(2) and stopped == ['owned-peer']


def test_native_recording_close_failure_keeps_container_for_retry():
    from je_auto_control.utils.remote_desktop.session_recorder import SessionRecorder

    class Container:
        closes = 0

        def close(self):
            self.closes += 1
            if self.closes == 1:
                raise OSError('controlled container close failure')

    recorder = SessionRecorder('unused.mp4')
    container = Container()
    recorder._container = container
    with pytest.raises(OSError, match='controlled container close failure'):
        recorder.stop()
    assert recorder._container is container and recorder._closed
    recorder.stop()
    assert container.closes == 2 and recorder._container is None


def test_x11_owned_subscription_does_not_stop_legacy_recording():
    import ast
    import threading
    import types
    import uuid
    from pathlib import Path
    from queue import Queue

    source = Path('je_auto_control/linux_with_x11/listener/x11_linux_listener.py').read_text(encoding='utf-8')
    handler = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef)
                   and node.name == 'KeypressHandler')
    event = types.SimpleNamespace(type=3, detail=38, root_x=10, root_y=20)
    parser = types.SimpleNamespace(parse_binary_value=lambda *args: (event, b''))
    scope = {'Queue': Queue, 'Optional': __import__('typing').Optional, 'Lock': threading.Lock,
             'uuid': uuid, 'X': types.SimpleNamespace(ButtonRelease=5, KeyRelease=3),
             'rq': types.SimpleNamespace(EventField=lambda value: parser),
             'current_display': types.SimpleNamespace(display=None)}
    exec(compile(ast.Module(body=[handler], type_ignores=[]), '<controlled X11 handler>', 'exec'), scope)
    native = scope['KeypressHandler']()
    owned, borrowed = Queue(), Queue()
    native.record(borrowed)
    identifier = native._subscribe_recording(owned)
    native.handle_reply(types.SimpleNamespace(data=b'event'))
    native._unsubscribe_recording(identifier)
    native.handle_reply(types.SimpleNamespace(data=b'event'))
    assert owned.qsize() == 1 and borrowed.qsize() == 2
    assert native.record_flag and native.record_queue is borrowed and native.still_listener


def test_executor_sleep_wakes_when_the_gui_task_is_cancelled():
    _probe('''
from je_auto_control.utils.executor.action_executor import Executor
started=threading.Event()
def work(token):
    started.set()
    return Executor().execute_action([['AC_sleep',{'seconds':30}]],raise_on_error=True)
handle=controller.submit(work,owner=owner);pump(started.is_set)
start=time.monotonic();handle.cancel();pump(lambda:not handle.is_running)
assert time.monotonic()-start < 1 and handle.result is None
''')


def test_close_waits_for_native_session_allocation_without_blocking_qt():
    _probe('''
from functools import partial
from je_auto_control.gui.remote_desktop._task_work import connect_owned
from je_auto_control.gui.remote_desktop.session_owner import PanelSessions
from je_auto_control.utils.remote_desktop.registry import _RemoteDesktopRegistry
native=_RemoteDesktopRegistry();sessions=PanelSessions(owner,native)
started=threading.Event();release=threading.Event();stopped=threading.Event();events=[]
class Viewer:
    def connect(self,timeout):
        started.set();release.wait(1);events.append('allocated')
    def disconnect(self,timeout=2):
        events.append('closed');stopped.set()
viewer=Viewer();session=sessions.reserve('tcp','viewer');sessions.attach(viewer,'viewer',active=False)
handle=controller.submit(partial(connect_owned,native,session,viewer.connect),owner=owner)
pump(started.is_set);start=time.monotonic();sessions.close('viewer')
assert time.monotonic()-start < .1 and not stopped.is_set()
release.set();pump(stopped.is_set)
assert events==['allocated','closed'] and handle.result is None
''')
