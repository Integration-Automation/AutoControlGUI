"""The Windows UIA backend from more than one thread (fake ``comtypes``; no COM, no desktop).

The backend kept one automation object on the instance and relied on COM
having been initialised wherever ``comtypes`` was first imported. A script
started from the GUI now runs on a worker thread, where ``AC_a11y_*`` used an
object the GUI thread had created, on a thread COM had never been initialised
on. ``comtypes`` is not installed where these tests were written, so they
model the one property that matters: every fake COM object remembers the
thread that created it and refuses -- and records -- any use from another.

What this cannot show is how the real UIAutomation behaves; see the module
docstring of ``windows_automation``.
"""
import gc
import sys
import threading
import types
import weakref

import pytest

from je_auto_control.utils.accessibility import backends
from je_auto_control.utils.accessibility.backends import windows_automation
from je_auto_control.utils.accessibility.backends import windows_backend as backend_module
from je_auto_control.utils.accessibility.backends.windows_automation import (
    APARTMENT_EXISTING, APARTMENT_MTA, APARTMENT_NONE, APARTMENT_STA, COINIT_APARTMENTTHREADED,
    COINIT_MULTITHREADED, PerThread, enter_apartment,
)
from je_auto_control.utils.accessibility.element import AccessibilityNotAvailableError
from headless._uia_doubles import Rect, UiaModule

_VALUE_PATTERN, _INVOKE_PATTERN, _TOGGLE_PATTERN = 10002, 10000, 10015
_CHANGED_MODE = 0x80010106
_IS_PASSWORD = 30019


class _World:
    """Everything the fakes record: who created what, every call, and every use from the wrong thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.calls, self.violations, self.automations, self.initialised = [], [], [], []

    def note(self, kind, name, owner):
        me = threading.get_ident()
        with self.lock:
            self.calls.append((kind, name, me))
            if me != owner:
                self.violations.append(f"{kind}.{name} used on thread {me}, created on {owner}")
        if me != owner:
            raise OSError("RPC_E_WRONG_THREAD")     # what the backend would swallow as "not found"


class _Bound:
    """A COM object: it belongs to the thread that created it."""

    def __init__(self, world):
        self._world, self._owner = world, threading.get_ident()

    def __getattribute__(self, name):
        if not name.startswith("_"):
            world = object.__getattribute__(self, "_world")
            world.note(type(self).__name__, name, object.__getattribute__(self, "_owner"))
        return object.__getattribute__(self, name)


class _Pattern(_Bound):
    def __init__(self, world, value="hello"):
        super().__init__(world)
        self.CurrentValue, self.done = value, []    # noqa: N815  # reason: the UIA name

    def SetValue(self, value):      # noqa: N802  # reason: the UIA name
        self.done.append(("set", value))

    def Invoke(self):               # noqa: N802  # reason: the UIA name
        self.done.append(("invoke",))

    def Toggle(self):               # noqa: N802  # reason: the UIA name
        self.done.append(("toggle",))


class _Unknown(_Bound):
    def __init__(self, world):
        super().__init__(world)
        self._pattern = _Pattern(world)

    def QueryInterface(self, _interface):   # noqa: N802  # reason: the COM name
        return self._pattern


class _Element(_Bound):
    def __init__(self, world, name, children=()):
        super().__init__(world)
        self._children = list(children)
        for prefix in ("Current", "Cached"):
            setattr(self, prefix + "Name", name)
            setattr(self, prefix + "ControlType", 50000)
            setattr(self, prefix + "BoundingRectangle", Rect(0, 0, 10, 20))
            setattr(self, prefix + "ProcessId", 7)
            setattr(self, prefix + "AutomationId", name.lower())
            setattr(self, prefix + "IsEnabled", True)
        self.focused = 0

    def GetCurrentPattern(self, pattern_id):    # noqa: N802  # reason: the UIA name
        known = (_VALUE_PATTERN, _INVOKE_PATTERN, _TOGGLE_PATTERN)
        return _Unknown(self._world) if pattern_id in known else None

    def GetCurrentPropertyValue(self, property_id):     # noqa: N802  # reason: the UIA name
        return False if property_id == _IS_PASSWORD else None

    def SetFocus(self):     # noqa: N802  # reason: the UIA name
        self.focused += 1


class _Request(_Bound):
    def AddProperty(self, _property_id):    # noqa: N802  # reason: the UIA name
        return None


class _Walker(_Bound):
    def GetFirstChildElementBuildCache(self, node, _request):   # noqa: N802  # reason: the UIA name
        children = node._children
        return children[0] if children else None

    def GetNextSiblingElementBuildCache(self, _child, _request):    # noqa: N802  # reason: the UIA name
        return None


class _Automation(_Bound):
    def __init__(self, world):
        super().__init__(world)
        self.ConnectionTimeout = None       # noqa: N815  # reason: the UIA name
        self.ControlViewWalker = _Walker(world)     # noqa: N815  # reason: the UIA name
        self._handlers = []

    def ElementFromHandle(self, _hwnd):     # noqa: N802  # reason: the UIA name
        return _Element(self._world, "Editor", [_Element(self._world, "Field")])

    def CreateCacheRequest(self):           # noqa: N802  # reason: the UIA name
        return _Request(self._world)

    def GetFocusedElement(self):            # noqa: N802  # reason: the UIA name
        return _Element(self._world, "Field")

    def AddFocusChangedEventHandler(self, _request, handler):   # noqa: N802  # reason: the UIA name
        self._handlers.append(handler)

    def RemoveFocusChangedEventHandler(self, handler):          # noqa: N802  # reason: the UIA name
        self._handlers.remove(handler)


@pytest.fixture()
def world(monkeypatch):
    """A fake ``comtypes`` whose objects are thread-bound, and a recorder in place of ``CoInitializeEx``."""
    state = _World()

    def co_create_instance(_clsid, interface=None):
        automation = _Automation(state)
        with state.lock:
            state.automations.append((threading.get_ident(), automation))
        return automation

    def co_initialize(flags):
        with state.lock:
            state.initialised.append((threading.get_ident(), flags))
            state.calls.append(("COM", "CoInitializeEx", threading.get_ident()))
        return 0

    comtypes = types.ModuleType("comtypes")
    comtypes.CoCreateInstance = co_create_instance
    comtypes.GUID = lambda text: text
    comtypes.COMObject = type("COMObject", (), {})
    client = types.ModuleType("comtypes.client")
    client.GetModule = lambda _name: UiaModule()
    comtypes.client = client
    monkeypatch.setitem(sys.modules, "comtypes", comtypes)
    monkeypatch.setitem(sys.modules, "comtypes.client", client)
    monkeypatch.setattr(windows_automation, "_system_co_initialize", co_initialize)
    monkeypatch.setattr(windows_automation, "_entered", threading.local())
    monkeypatch.setattr(backend_module, "_process_name", lambda pid: f"app{pid}.exe")

    def search_roots(automation, _window_title):
        yield automation.ElementFromHandle(1)

    monkeypatch.setattr(backend_module, "search_roots", search_roots)
    return state


@pytest.fixture()
def backend(world):
    return backend_module.WindowsAccessibilityBackend()


def _on_thread(call):
    """Run ``call`` on a new thread; return ``(thread id, result)`` or re-raise what it raised."""
    box = {}

    def run():
        box["ident"] = threading.get_ident()
        try:
            box["result"] = call()
        except BaseException as error:  # noqa: BLE001  # reason: re-raised below, on the test's thread
            box["error"] = error

    thread = threading.Thread(target=run, name="uia-test-worker")
    thread.start()
    thread.join(30.0)
    assert not thread.is_alive()
    if "error" in box:
        raise box["error"]
    return box["ident"], box["result"]


# --- the backend -------------------------------------------------------------------------------------------------

def test_an_object_made_on_one_thread_is_never_used_on_another(backend, world):
    """The reported defect: first use on the GUI thread, then ``AC_a11y_*`` from a script's worker thread."""
    assert [element.name for element in backend.list_elements()] == ["Editor", "Field"]
    worker, names = _on_thread(lambda: [element.name for element in backend.list_elements()])
    assert names == ["Editor", "Field"]
    assert world.violations == []
    assert [ident for ident, _automation in world.automations] == [threading.get_ident(), worker]


def test_the_doubles_catch_what_the_backend_used_to_do(world):
    """One object kept on the instance, as before: the second thread's use of it is refused and recorded."""

    class _Shared(backend_module.WindowsAccessibilityBackend):
        _automation = None                              # an ordinary attribute again

    shared = _Shared()
    assert [element.name for element in shared.list_elements()] == ["Editor", "Field"]
    with pytest.raises(OSError, match="RPC_E_WRONG_THREAD"):
        _on_thread(shared.list_elements)
    assert world.violations and "_Automation.ElementFromHandle" in world.violations[0]
    assert len(world.automations) == 1


def test_each_thread_initialises_com_before_its_first_com_call(backend, world):
    backend.list_elements()
    backend.list_elements()                             # the same thread again: nothing new
    first, _ = _on_thread(backend.list_elements)
    second, _ = _on_thread(backend.list_elements)
    main = threading.get_ident()
    assert world.initialised == [(main, COINIT_APARTMENTTHREADED), (first, COINIT_MULTITHREADED),
                                 (second, COINIT_MULTITHREADED)]
    for ident in (main, first, second):
        on_thread = [(kind, name) for kind, name, thread in world.calls if thread == ident]
        assert on_thread[0] == ("COM", "CoInitializeEx"), on_thread[:3]
    assert len(world.automations) == 3 and world.violations == []


def test_every_read_and_action_stays_on_the_calling_thread(backend, world):
    backend.focused_element()                           # the main thread has its own object by now

    def use_everything():
        return {
            "value": backend.get_value(name="Field"),
            "set": backend.set_value("typed", name="Field"),
            "invoke": backend.invoke(name="Field"),
            "toggle": backend.toggle(name="Field"),
            "focus": backend.set_focus(name="Field"),
            "focused": backend.focused_element().name,
            "state": backend.get_state(name="Field") is not None,
            "by_id": backend.get_value(automation_id="field"),
        }

    worker, results = _on_thread(use_everything)
    assert results == {"value": "hello", "set": True, "invoke": True, "toggle": True, "focus": True,
                       "focused": "Field", "state": True, "by_id": "hello"}
    assert world.violations == []
    assert {thread for _kind, _name, thread in world.calls} == {threading.get_ident(), worker}


def test_many_threads_at_once_each_keep_to_their_own_objects(backend, world):
    start, results, errors = threading.Barrier(6), [], []

    def run():
        try:
            start.wait(10.0)
            for _ in range(5):
                results.append((backend.get_value(name="Field"), len(backend.list_elements())))
        except BaseException as error:  # noqa: BLE001  # reason: reported by the assertion below
            errors.append(error)

    threads = [threading.Thread(target=run) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30.0)
    assert errors == [] and results == [("hello", 2)] * 30
    assert world.violations == [] and len(world.automations) == 6


def test_a_focus_subscription_is_added_and_removed_on_the_thread_that_waits(backend, world, monkeypatch):
    monkeypatch.setattr(backend, "_make_focus_handler", lambda sink: object())
    worker, result = _on_thread(lambda: backend.wait_for_focus_change(timeout=0.01))
    assert result is None and world.violations == []
    events = [(name, thread) for kind, name, thread in world.calls
              if kind == "_Automation" and "FocusChangedEventHandler" in name]
    assert events == [("AddFocusChangedEventHandler", worker), ("RemoveFocusChangedEventHandler", worker)]
    assert [automation._handlers for ident, automation in world.automations if ident == worker] == [[]]


def test_a_threads_automation_object_goes_when_the_thread_ends(backend, world):
    _on_thread(backend.list_elements)
    seen = weakref.ref(world.automations[0][1])
    del world.automations[:]
    del world.calls[:]
    gc.collect()
    assert seen() is None, "the object of a thread that ended was kept alive"
    assert backend._automation is None                  # and this thread never had one


def test_the_executor_command_works_from_a_worker_thread_after_the_main_thread_used_it(backend, world,
                                                                                    monkeypatch):
    """``AC_a11y_*`` in a script the GUI started: the path that had never run."""
    from je_auto_control.utils.executor.action_executor import executor
    monkeypatch.setattr(backends, "_cached_backend", backend)
    listed = executor.event_dict["AC_a11y_list"]()
    assert [row["name"] for row in listed] == ["Editor", "Field"]
    _worker, record = _on_thread(lambda: executor.execute_action([["AC_a11y_list", {}], ["AC_a11y_focused", {}]]))
    assert world.violations == []
    assert len(world.automations) == 2
    answers = list(record.values())
    assert [row["name"] for row in answers[0]] == ["Editor", "Field"] and answers[1]["name"] == "Field"


# --- the apartment -----------------------------------------------------------------------------------------------

@pytest.fixture()
def fresh_thread_state(monkeypatch):
    monkeypatch.setattr(windows_automation, "_entered", threading.local())


def test_the_main_thread_is_single_threaded_and_a_worker_joins_the_mta(fresh_thread_state):
    asked = []

    def co_initialize(flags):
        asked.append(flags)
        return 0

    assert enter_apartment(co_initialize) == APARTMENT_STA
    assert enter_apartment(co_initialize) == APARTMENT_STA      # once per thread
    assert _on_thread(lambda: enter_apartment(co_initialize))[1] == APARTMENT_MTA
    assert asked == [COINIT_APARTMENTTHREADED, COINIT_MULTITHREADED]


def test_a_thread_already_initialised_is_used_as_it_is(fresh_thread_state):
    assert enter_apartment(lambda _flags: 1) == APARTMENT_STA           # S_FALSE: same mode, already there
    assert _on_thread(lambda: enter_apartment(lambda _flags: _CHANGED_MODE))[1] == APARTMENT_EXISTING
    # The signed spelling ctypes gives a failed HRESULT.
    assert _on_thread(lambda: enter_apartment(lambda _flags: _CHANGED_MODE - (1 << 32)))[1] == APARTMENT_EXISTING


def test_a_com_that_will_not_initialise_is_a_typed_error_and_is_asked_again(fresh_thread_state):
    answers = [0x8007000E, 0]                                           # E_OUTOFMEMORY, then S_OK
    with pytest.raises(AccessibilityNotAvailableError, match="0x8007000e"):
        enter_apartment(lambda _flags: answers.pop(0))
    assert enter_apartment(lambda _flags: answers.pop(0)) == APARTMENT_STA


def test_where_there_is_no_com_nothing_is_initialised(fresh_thread_state):
    assert enter_apartment(lambda _flags: None) == APARTMENT_NONE


@pytest.mark.skipif(sys.platform == "win32", reason="on Windows the real call runs")
def test_off_windows_the_system_call_is_not_attempted(fresh_thread_state):
    assert windows_automation._system_co_initialize(COINIT_MULTITHREADED) is None
    assert enter_apartment() == APARTMENT_NONE


# --- the per-thread attribute ------------------------------------------------------------------------------------

class _Holder:
    slot = PerThread()


def test_a_per_thread_attribute_is_one_value_per_thread_and_per_instance():
    first, second = _Holder(), _Holder()
    assert first.slot is None
    first.slot = "main"
    assert _on_thread(lambda: first.slot)[1] is None
    assert _on_thread(lambda: (setattr(first, "slot", "worker"), first.slot)[1])[1] == "worker"
    assert first.slot == "main" and second.slot is None
    assert isinstance(_Holder.slot, PerThread)
