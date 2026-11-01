"""Create a key file only its owner can read, and notice one that others can.

POSIX has the mode bits: ``os.open(..., 0o600)`` creates the file private in
one call. Windows ignores them -- a new file takes the access list of its
directory, so a private signing key created outside the user's profile was
readable by whoever the directory let in, and nothing looked. Here the file
is created with an explicit, protected access list that names the current
user and nobody else, in the same ``CreateFileW`` call that creates it: there
is no moment at which it exists with the inherited list, so no handle opened
in between outlives the restriction. ``icacls`` would be a child process and
a second step.

A key that was created some other way -- by an earlier version, copied in,
restored from a backup -- is not touched. :func:`exposure` says who else can
read it and :func:`warn_if_exposed` logs that once per file when the key is
loaded.

Standard library only (``ctypes`` on Windows); imports no ``PySide6``.
"""
import ctypes
import importlib
import os
import re
import stat
import sys
import threading
from pathlib import Path
from typing import Any, List, Optional, Set

from je_auto_control.utils.logging.logging_instance import autocontrol_logger

# Well-known groups that mean "more than this user": SDDL alias -> (SID, name).
_BROAD_PRINCIPALS = {
    "WD": ("S-1-1-0", "Everyone"),
    "AU": ("S-1-5-11", "Authenticated Users"),
    "BU": ("S-1-5-32-545", "Users"),
    "IU": ("S-1-5-4", "Interactive"),
    "AN": ("S-1-5-7", "Anonymous"),
    "BG": ("S-1-5-32-546", "Guests"),
    "NU": ("S-1-5-2", "Network"),
}
_BROAD_BY_SID = dict(_BROAD_PRINCIPALS.values())
# Two-letter SDDL rights that include reading the file's data.
_READ_RIGHTS = frozenset({"FA", "FR", "GA", "GR", "CC"})
_FILE_READ_DATA = 0x1
_GENERIC_READ = 0x80000000
_GENERIC_ALL = 0x10000000
_ACE = re.compile(r"\(([^()]*)\)")

_SE_FILE_OBJECT = 1
_DACL_SECURITY_INFORMATION = 0x4
_SDDL_REVISION_1 = 1
_TOKEN_QUERY = 0x8
_TOKEN_USER = 1
_GENERIC_WRITE = 0x40000000
_SHARE_ALL = 0x7  # read | write | delete, what the C runtime's open shares
_CREATE_NEW = 1
_FILE_ATTRIBUTE_NORMAL = 0x80
_ERROR_FILE_EXISTS = 80
_ERROR_ALREADY_EXISTS = 183

_warned: Set[str] = set()
_warned_lock = threading.Lock()


def _is_windows() -> bool:
    return sys.platform == "win32"


def open_new_private_file(path: Path) -> int:
    """Create ``path`` for writing, readable by its owner only; return the descriptor.

    Raises :class:`FileExistsError` when ``path`` exists -- creation is
    exclusive on both platforms. On Windows, if the access list cannot be
    applied (a share or filesystem without one) the file is created the
    ordinary way and that is logged; it is then no worse off than before.
    """
    if _is_windows():
        try:
            return _windows_create_private(path)
        except FileExistsError:
            raise
        except OSError as error:
            autocontrol_logger.warning(
                "could not restrict %s to the current user (%r); "
                "it inherits its directory's permissions", path, error)
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)


def exposure(path: Path) -> List[str]:
    """Who, besides its owner, can read the file at ``path``; empty when nobody.

    On POSIX the answer comes from the mode bits (``"group"``, ``"others"``);
    on Windows from the access list (``"Users"``, ``"Everyone"`` ...). A file
    that cannot be inspected is reported as not exposed: this is a warning
    aid, not a gate.
    """
    try:
        if _is_windows():
            return broad_readers(_windows_dacl_sddl(path))
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError as error:
        autocontrol_logger.debug("could not inspect permissions of %s: %r", path, error)
        return []
    return [who for bit, who in ((stat.S_IRGRP, "group"), (stat.S_IROTH, "others"))
            if mode & bit]


def warn_if_exposed(path: Path, what: str) -> List[str]:
    """Log, once per file, that the secret ``what`` at ``path`` is readable by others."""
    readers = exposure(path)
    if not readers:
        return readers
    key = os.path.normcase(os.path.abspath(str(path)))
    with _warned_lock:
        if key in _warned:
            return readers
        _warned.add(key)
    autocontrol_logger.warning(
        "%s %s is readable by %s; restrict it to the account that uses it "
        "(Windows: icacls <file> /inheritance:r /grant:r <user>:F; POSIX: chmod 600)",
        what, path, ", ".join(readers))
    return readers


def broad_readers(sddl: str) -> List[str]:
    """The well-known groups a DACL in SDDL form lets read the file.

    Only access-allowed entries that apply to the file itself count; an
    inherit-only entry describes what children would get. A file with no
    access list at all (``NO_ACCESS_CONTROL``) is open to everyone.
    """
    _, _, dacl = sddl.partition("D:")
    if "NO_ACCESS_CONTROL" in dacl:
        return ["Everyone"]
    found: List[str] = []
    for ace in _ACE.findall(dacl):
        fields = ace.split(";")
        if len(fields) != 6 or fields[0] != "A" or "IO" in _pairs(fields[1]):
            continue
        name = _broad_name(fields[5])
        if name is not None and name not in found and _grants_read(fields[2]):
            found.append(name)
    return found


def _pairs(text: str) -> List[str]:
    return [text[index:index + 2] for index in range(0, len(text), 2)]


def _broad_name(sid: str) -> Optional[str]:
    alias = _BROAD_PRINCIPALS.get(sid.upper())
    return alias[1] if alias is not None else _BROAD_BY_SID.get(sid.upper())


def _grants_read(rights: str) -> bool:
    if rights.lower().startswith("0x"):
        try:
            mask = int(rights, 16)
        except ValueError:
            return True  # unreadable rights on a broad group: say so rather than hide it
        return bool(mask & (_FILE_READ_DATA | _GENERIC_READ | _GENERIC_ALL))
    return any(pair in _READ_RIGHTS for pair in _pairs(rights.upper()))


# --- Windows -------------------------------------------------------------------------------

class _SecurityAttributes(ctypes.Structure):
    _fields_ = [("nLength", ctypes.c_uint32),
                ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", ctypes.c_int)]


def _dll(name: str) -> Any:
    """``ctypes.WinDLL(name)`` with last-error tracking; Windows only."""
    return getattr(ctypes, "WinDLL")(name, use_last_error=True)


def _last_error(code: Optional[int] = None) -> OSError:
    number = getattr(ctypes, "get_last_error")() if code is None else code
    return getattr(ctypes, "WinError")(number)


def _local_free(kernel32: Any, pointer: Any) -> None:
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))


def _current_user_sid() -> str:
    """The string SID (``S-1-5-21-...``) of the account this process runs as."""
    advapi32, kernel32 = _dll("advapi32"), _dll("kernel32")
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    advapi32.OpenProcessToken.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
    token = ctypes.c_void_p()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), _TOKEN_QUERY,
                                     ctypes.byref(token)):
        raise _last_error()
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    try:
        advapi32.GetTokenInformation.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_uint32)]
        needed = ctypes.c_uint32(0)
        advapi32.GetTokenInformation(token, _TOKEN_USER, None, 0, ctypes.byref(needed))
        if not needed.value:
            raise _last_error()
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(token, _TOKEN_USER, buffer, needed.value,
                                            ctypes.byref(needed)):
            raise _last_error()
        # TOKEN_USER starts with SID_AND_ATTRIBUTES, whose first member is the PSID.
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents
        text = ctypes.c_wchar_p()
        advapi32.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
        if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise _last_error()
        try:
            return str(text.value)
        finally:
            _local_free(kernel32, text)
    finally:
        kernel32.CloseHandle(token)


def _windows_create_private(path: Path) -> int:
    """``CreateFileW(CREATE_NEW)`` with a DACL naming the current user only."""
    advapi32, kernel32 = _dll("advapi32"), _dll("kernel32")
    # P: protected (inherits nothing). One entry: full access for this account.
    sddl = f"D:P(A;;FA;;;{_current_user_sid()})"
    descriptor = ctypes.c_void_p()
    convert = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32,
                        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    if not convert(sddl, _SDDL_REVISION_1, ctypes.byref(descriptor), None):
        raise _last_error()
    try:
        attributes = _SecurityAttributes(
            ctypes.sizeof(_SecurityAttributes), descriptor.value, 0)
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
        kernel32.CreateFileW.restype = ctypes.c_void_p
        handle = kernel32.CreateFileW(
            str(path), _GENERIC_WRITE, _SHARE_ALL, ctypes.byref(attributes),
            _CREATE_NEW, _FILE_ATTRIBUTE_NORMAL, None)
        if handle is None or handle == ctypes.c_void_p(-1).value:
            code = getattr(ctypes, "get_last_error")()
            if code in (_ERROR_FILE_EXISTS, _ERROR_ALREADY_EXISTS):
                raise FileExistsError(f"{str(path)!r} already exists")
            raise _last_error(code)
    finally:
        _local_free(kernel32, descriptor)
    msvcrt = importlib.import_module("msvcrt")
    return int(msvcrt.open_osfhandle(handle, os.O_WRONLY | getattr(os, "O_BINARY", 0)))


def _windows_dacl_sddl(path: Path) -> str:
    """The file's discretionary access list as an SDDL string."""
    advapi32, kernel32 = _dll("advapi32"), _dll("kernel32")
    descriptor = ctypes.c_void_p()
    advapi32.GetNamedSecurityInfoW.argtypes = [
        ctypes.c_wchar_p, ctypes.c_int, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.GetNamedSecurityInfoW.restype = ctypes.c_uint32
    code = advapi32.GetNamedSecurityInfoW(
        str(path), _SE_FILE_OBJECT, _DACL_SECURITY_INFORMATION, None, None, None, None,
        ctypes.byref(descriptor))
    if code != 0:
        raise _last_error(code)
    try:
        text = ctypes.c_wchar_p()
        convert = advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW
        convert.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                            ctypes.POINTER(ctypes.c_wchar_p), ctypes.c_void_p]
        if not convert(descriptor, _SDDL_REVISION_1, _DACL_SECURITY_INFORMATION,
                       ctypes.byref(text), None):
            raise _last_error()
        try:
            return str(text.value)
        finally:
            _local_free(kernel32, text)
    finally:
        _local_free(kernel32, descriptor)


__all__ = ["broad_readers", "exposure", "open_new_private_file", "warn_if_exposed"]
