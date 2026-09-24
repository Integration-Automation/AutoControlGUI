"""A restart must never revive the run that ``stop()`` gave up waiting for.

Every background service here stops the same way: set an event, join the
thread with a timeout, forget the thread. And every one used to start the same
way: ``self._stop.clear()``, then a new thread. When the join timed out -- the
loop was inside a long iteration: a scheduled job, a hotkey action, a slow
enumeration -- the old thread was still alive, and the next ``start()`` cleared
the very event it was waiting to see. It carried on beside the new one,
untracked, for the life of the process: the scheduler ran every job twice, the
hotkey daemon fired every binding twice, the popup watchdog clicked twice.

The fix is one event per run, handed to the loop as an argument. The invariant
pinned here: once a run's event is set, no later ``start()`` clears it.

No loop runs. Each module's ``threading.Thread`` is replaced by a thread that
never starts and never finishes -- exactly what ``stop()`` sees when the loop
is stuck -- so the case costs nothing and touches no clipboard, screen or
hotkey.
"""
import threading
import types
from typing import Any, Callable, List

import pytest


class _StuckThread:
    """A thread whose loop is blocked: never finishes, ``join`` times out."""

    created: List["_StuckThread"] = []

    def __init__(self, target=None, args=(), kwargs=None, name=None,
                 daemon=None):
        self.target = target
        self.args = tuple(args)
        self.name = name
        self.daemon = daemon
        _StuckThread.created.append(self)

    def start(self) -> None:
        """Nothing runs: the loop is modelled as stuck from the start."""

    def join(self, timeout=None) -> None:
        """Returns at once, as a join that timed out would."""

    def is_alive(self) -> bool:
        return True


def _run_event(thread: _StuckThread) -> threading.Event:
    """The stop event a run's loop was handed."""
    for arg in thread.args:
        if isinstance(arg, threading.Event):
            return arg
        stop_event = getattr(arg, "stop_event", None)
        if isinstance(stop_event, threading.Event):
            return stop_event
    raise AssertionError(
        f"{thread.name}: the loop was not handed its own stop event, so it "
        f"can only read the shared one -- the one start() replaces")


def _stuck_threads(monkeypatch, module) -> None:
    proxy = types.SimpleNamespace(
        **{name: getattr(threading, name) for name in dir(threading)
           if not name.startswith("__")})
    proxy.Thread = _StuckThread
    monkeypatch.setattr(module, "threading", proxy)


def _accessibility(tmp_path):
    from je_auto_control.utils.accessibility import recorder as module
    return module, module.AccessibilityRecorder(fetcher=lambda *_: [])


def _clipboard(tmp_path):
    from je_auto_control.utils.clipboard_history import clipboard_history as module
    return module, module.ClipboardHistory()


def _plugin_watcher(tmp_path):
    from je_auto_control.utils.mcp_server import plugin_watcher as module
    return module, module.PluginWatcher(server=None, directory=str(tmp_path))


def _observer(tmp_path):
    from je_auto_control.utils.observer import observer as module
    return module, module.ScreenObserver()


def _profiler(tmp_path):
    from je_auto_control.utils.profiler import resource_profiler as module
    profiler = module.ResourceProfiler()
    # Without psutil start() runs no thread at all; pretend it is there.
    profiler._psutil = object()
    profiler._proc = None
    return module, profiler


def _folder_sync(tmp_path):
    from je_auto_control.utils.remote_desktop import file_sync as module
    return module, module.FolderSyncEngine(watch_dir=tmp_path,
                                           sender=lambda *_: None)


def _scheduler(tmp_path):
    from je_auto_control.utils.scheduler import scheduler as module
    return module, module.Scheduler(executor=lambda *_: None)


def _renewal(tmp_path):
    from je_auto_control.utils.tls_acme import renewal as module
    return module, module.RenewalScheduler(tmp_path / "cert.pem",
                                           renew=lambda: None)


def _email_trigger(tmp_path):
    from je_auto_control.utils.triggers import email_trigger as module
    return module, module.EmailTriggerWatcher(executor=lambda *_: None)


def _trigger_engine(tmp_path):
    from je_auto_control.utils.triggers import trigger_engine as module
    return module, module.TriggerEngine(executor=lambda *_: None)


def _loopback(tmp_path):
    from je_auto_control.utils.usb.passthrough import loopback as module
    return module, module.LoopbackTransport(session=None)


def _popup_watchdog(tmp_path):
    from je_auto_control.utils.watchdog import popup_watchdog as module
    return module, module.PopupWatchdog()


def _hotkey_daemon(tmp_path):
    from je_auto_control.utils.hotkey import hotkey_daemon as module
    return module, module.HotkeyDaemon(executor=lambda *_: None)


def _usbip_server(tmp_path):
    from je_auto_control.utils.usbip import server as module
    return module, module.UsbIpServer(backend=None, port=0)


SERVICES: List[Callable[[Any], Any]] = [
    _accessibility, _clipboard, _plugin_watcher, _observer, _profiler,
    _folder_sync, _scheduler, _renewal, _email_trigger, _trigger_engine,
    _loopback, _popup_watchdog, _hotkey_daemon, _usbip_server,
]


@pytest.mark.parametrize("build", SERVICES,
                         ids=[build.__name__.lstrip("_") for build in SERVICES])
def test_restart_does_not_revive_the_stuck_run(monkeypatch, tmp_path, build):
    module, service = build(tmp_path)
    _stuck_threads(monkeypatch, module)
    _StuckThread.created.clear()

    service.start()
    first = _run_event(_StuckThread.created[0])
    service.stop()
    assert first.is_set(), "stop() did not signal the run it stopped"

    service.start()                       # the old loop is still stuck
    try:
        assert first.is_set(), (
            "start() cleared the event the stuck loop is waiting on: it will "
            "resume beside the new run")
        second = _run_event(_StuckThread.created[-1])
        assert second is not first and not second.is_set()
    finally:
        service.stop()


def test_slack_bot_second_run_leaves_the_first_stopped(monkeypatch):
    """``run_forever`` runs on the caller's thread, so it is tested directly."""
    from je_auto_control.utils.chatops import slack_bot as module
    bot = module.SlackBot(token="xoxb-test", channel_id="C0", router=None)
    bot.poll_interval_s = 0.0          # past __post_init__'s floor, on purpose

    first_run: List[threading.Event] = []

    def first_poll():
        first_run.append(bot._stop)
        bot.stop()

    monkeypatch.setattr(bot, "poll_once", first_poll)
    bot.run_forever()
    monkeypatch.setattr(bot, "poll_once", lambda: None)
    bot.run_forever(max_iterations=1)
    assert first_run and first_run[0].is_set(), (
        "the second run_forever() cleared the first run's event")
