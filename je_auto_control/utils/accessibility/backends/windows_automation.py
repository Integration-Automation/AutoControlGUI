"""The UIAutomation object, and which thread may use it.

COM objects have thread affinity. The backend used to create one
``CUIAutomation`` on first use and keep it on the instance, with COM
initialised only on the thread that happened to import ``comtypes``. That held
while every caller was the same thread; it stopped holding when scripts started
from the GUI moved to worker threads, where ``AC_a11y_*`` then used an object
another thread had created, on a thread COM had never been initialised on.

The rule here is **one automation object per calling thread**: a thread that
asks for it first joins a COM apartment (:func:`enter_apartment`) and then
creates its own object (:class:`PerThread` keeps one value per thread on the
backend instance). That is enough because no raw COM pointer outlives a call
of the backend -- every public method finds its element, acts on it and
answers with plain data -- so nothing is ever handed from one thread to
another, and a focus subscription is added and removed inside one call, on
one thread.

A single owner thread that every call is marshalled to was the alternative. It
was not taken for two reasons. A caller blocked waiting for the owner cannot
answer UIA's own questions: a desktop listing includes the caller's windows,
and a GUI thread parked on a queue would stall each of those providers until
its timeout. And it would move the one path known to work -- a script calling
from the main thread -- onto a different thread, which no machine without
``comtypes`` and a desktop to try it on could confirm.

The apartment: the main thread is initialised single-threaded, which is what
``comtypes`` itself does on import and what a GUI toolkit that arrives later
needs; every other thread joins the multi-threaded apartment, which needs no
message pump. A thread that already is in an apartment keeps it. COM is never
uninitialised here: the thread's object is released when the thread ends, and
uninitialising under a live object is the worse mistake.

Imports no ``PySide6``.
"""
import functools
import sys
import threading
from typing import Any, Callable, Optional

from je_auto_control.utils.accessibility.backends.windows_reads import UIA_READ_ERRORS
from je_auto_control.utils.accessibility.element import AccessibilityNotAvailableError
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

COINIT_MULTITHREADED = 0x0
COINIT_APARTMENTTHREADED = 0x2
_S_OK = 0
_S_FALSE = 1                            # already initialised on this thread, in the same mode
_RPC_E_CHANGED_MODE = 0x80010106        # already initialised on this thread, in the other mode

#: What :func:`enter_apartment` answers: the apartment this thread joined, the one it already was
#: in, or that there is no COM on this platform.
APARTMENT_MTA = "mta"
APARTMENT_STA = "sta"
APARTMENT_EXISTING = "existing"
APARTMENT_NONE = "none"

_entered = threading.local()


def _system_co_initialize(flags: int) -> Optional[int]:
    """``CoInitializeEx(NULL, flags)`` as an unsigned HRESULT; ``None`` where there is no COM.

    Never raises for a COM answer: "already initialised in the other mode"
    is a result the caller has a use for, not an error.
    """
    if sys.platform != "win32":
        return None
    import ctypes
    ole32 = ctypes.WinDLL("ole32")      # a private handle: argtypes set here do not leak to other users
    co_initialize = ole32.CoInitializeEx
    co_initialize.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    co_initialize.restype = ctypes.c_long
    return int(co_initialize(None, flags)) & 0xFFFFFFFF


def enter_apartment(co_initialize: Optional[Callable[[int], Optional[int]]] = None) -> str:
    """Initialise COM on the calling thread, once per thread; return which apartment it is in.

    Call it before the first COM call on a thread. ``co_initialize`` stands in
    for the system call in tests.
    """
    state = getattr(_entered, "state", None)
    if state is not None:
        return str(state)
    on_main = threading.current_thread() is threading.main_thread()
    answer = (co_initialize or _system_co_initialize)(
        COINIT_APARTMENTTHREADED if on_main else COINIT_MULTITHREADED)
    result = -1 if answer is None else answer & 0xFFFFFFFF
    if answer is None:
        state = APARTMENT_NONE
    elif result in (_S_OK, _S_FALSE):
        state = APARTMENT_STA if on_main else APARTMENT_MTA
    elif result == _RPC_E_CHANGED_MODE:
        state = APARTMENT_EXISTING      # a GUI toolkit or comtypes got here first: use what is there
    else:
        raise AccessibilityNotAvailableError(
            f"COM could not be initialised on thread {threading.current_thread().name!r}: 0x{result:08x}")
    _entered.state = state
    autocontrol_logger.debug("UIA: thread %s is in the %s apartment", threading.current_thread().name, state)
    return state


class PerThread:
    """An instance attribute with one value per thread; ``None`` on a thread that has not set it.

    A data descriptor, so ``self._automation = x`` and ``self._automation``
    read like an ordinary attribute -- but a thread only ever sees the object
    it stored itself, and the value is dropped when that thread ends.
    """

    def __set_name__(self, owner: type, name: str) -> None:
        self._key = f"_per_thread_{name}"

    def _slot(self, instance: Any) -> threading.local:
        slot = instance.__dict__.get(self._key)
        if slot is None:
            slot = instance.__dict__.setdefault(self._key, threading.local())
        return slot     # type: ignore[no-any-return]

    def __get__(self, instance: Any, owner: Optional[type] = None) -> Any:
        if instance is None:
            return self
        return getattr(self._slot(instance), "value", None)

    def __set__(self, instance: Any, value: Any) -> None:
        self._slot(instance).value = value


def _is_available() -> bool:
    try:
        import comtypes.client  # noqa: F401  # reason: probe import
        return True
    except ImportError:
        return False


# ``CUIAutomation8`` is the only class that hands out ``IUIAutomation2``, which
# is the only way to bound how long UIA waits for an application's provider.
# It matters: a full-screen game that never answers UIA made a single
# ``ElementFromHandle`` block for **60 seconds** here, poisoning every
# desktop-wide search. With the connection timeout set, the same call is 1.0 s.
_CLSID_CUIAUTOMATION8 = "{e22ad333-b25f-460c-83d0-0581107395c9}"
_CLSID_CUIAUTOMATION = "{ff48dba4-60ef-4201-aa87-54103eef594e}"
# Only the connect step is tightened. A provider that cannot even connect within
# a second is not going to answer; how long a legitimate *query* may take is a
# different question, so ``TransactionTimeout`` keeps its default.
_CONNECTION_TIMEOUT_MS = 1000


def _create_automation(uia_module: Any) -> Any:
    """The UIAutomation object, with a bounded provider-connect wait if possible."""
    from comtypes import CoCreateInstance, GUID
    interface = getattr(uia_module, "IUIAutomation2", None)
    if interface is not None:
        try:
            automation = CoCreateInstance(GUID(_CLSID_CUIAUTOMATION8),
                                          interface=interface)
            automation.ConnectionTimeout = _CONNECTION_TIMEOUT_MS
            return automation
        except UIA_READ_ERRORS as error:
            autocontrol_logger.info(
                "UIAutomation2 unavailable, provider waits are unbounded: %r",
                error)
    return CoCreateInstance(GUID(_CLSID_CUIAUTOMATION),
                            interface=uia_module.IUIAutomation)


@functools.lru_cache(maxsize=256)
def _process_name(process_id: int) -> str:
    """Executable name for a pid.

    Cached because a desktop listing asks for the same handful of pids
    thousands of times, and each miss is an ``OpenProcess`` /
    ``QueryFullProcessImageNameW`` / ``CloseHandle`` round trip. Windows does
    recycle pids, so a very long-lived session could in principle read a stale
    name here; it only labels ``app_name``, and the cache is bounded.
    """
    if process_id <= 0 or sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        process_query_information = 0x0400 | 0x0010
        handle = kernel32.OpenProcess(process_query_information, False, process_id)
        if not handle:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = wintypes.DWORD(len(buf))
            get_image = kernel32.QueryFullProcessImageNameW
            if not get_image(handle, 0, buf, ctypes.byref(size)):
                return ""
            return buf.value.rsplit("\\", 1)[-1]
        finally:
            kernel32.CloseHandle(handle)
    except OSError:
        return ""


__all__ = [
    "APARTMENT_EXISTING", "APARTMENT_MTA", "APARTMENT_NONE", "APARTMENT_STA", "PerThread", "enter_apartment",
]
