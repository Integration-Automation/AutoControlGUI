"""A private key file is readable by its owner only -- on Windows too.

POSIX creates the key 0600. Windows ignores mode bits: the key took its
directory's access list, so a signing key created outside the user's profile
could be read by whoever that directory admitted, and nothing checked. The
file is now created with an access list naming the current user only, and a
key that others can read is reported when it is loaded.

Two kinds of test: the access-list reader and the decisions around it run on
every platform against fakes; the ones marked Windows-only create a real file
in a temp directory and read its real access list back (no desktop involved).
"""
import logging
import os
import stat
import sys

import pytest

from je_auto_control.utils.action_signing import _key_file, _private_file
from je_auto_control.utils.action_signing._key_file import (
    load_or_create_key_file, write_new_file,
)
from je_auto_control.utils.action_signing._private_file import (
    broad_readers, exposure, open_new_private_file, warn_if_exposed,
)
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_USER = "S-1-5-21-1111111111-2222222222-3333333333-1001"
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="reads a real Windows DACL")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="mode bits are POSIX")


@pytest.fixture(autouse=True)
def _fresh_warnings():
    _private_file._warned.clear()
    yield
    _private_file._warned.clear()


@pytest.fixture
def warnings(caplog):
    caplog.set_level(logging.DEBUG, logger=autocontrol_logger.name)
    return lambda: [record.getMessage() for record in caplog.records
                    if record.levelno >= logging.WARNING]


# --- reading an access list (pure, every platform) ---------------------------------------

@pytest.mark.parametrize("sddl, expected", [
    (f"D:P(A;;FA;;;{_USER})", []),
    (f"D:PAI(A;;FA;;;{_USER})(A;;FA;;;SY)(A;;FA;;;BA)", []),
    (f"D:AI(A;ID;FA;;;{_USER})(A;ID;0x1200a9;;;BU)", ["Users"]),
    ("D:(A;;FR;;;WD)", ["Everyone"]),
    ("D:(A;;GR;;;AU)(A;;GA;;;S-1-5-32-545)", ["Authenticated Users", "Users"]),
    ("D:(A;;0x120089;;;S-1-1-0)", ["Everyone"]),
    ("O:BAG:BAD:(A;;FA;;;BA)(A;;FRFX;;;IU)", ["Interactive"]),
    ("D:NO_ACCESS_CONTROL", ["Everyone"]),
])
def test_broad_readers_names_the_groups_that_can_read(sddl, expected):
    assert broad_readers(sddl) == expected


@pytest.mark.parametrize("sddl", [
    "D:(D;;FA;;;WD)",                    # a deny entry grants nothing
    "D:(A;OICIIO;FA;;;BU)",              # inherit-only: for children, not this file
    "D:(A;;FW;;;BU)",                    # write without read
    "D:(A;;0x100116;;;AU)",              # write/append/sync, no read bit
    "D:(A;;FA;;;S-1-5-21-9-9-9-500)",    # some other single account is not a broad group
    "",
])
def test_broad_readers_ignores_entries_that_do_not_let_a_group_read(sddl):
    assert broad_readers(sddl) == []


def test_each_group_is_named_once():
    assert broad_readers("D:(A;;FR;;;BU)(A;ID;FA;;;BU)") == ["Users"]


# --- the decisions around it, with a fake platform ------------------------------------------

@pytest.fixture
def fake_windows(monkeypatch):
    """Pretend to be Windows; ``calls`` records what was asked of the platform layer."""
    calls = {"created": [], "sddl": f"D:P(A;;FA;;;{_USER})"}

    def create(path):
        calls["created"].append(path)
        return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    monkeypatch.setattr(_private_file, "_is_windows", lambda: True)
    monkeypatch.setattr(_private_file, "_windows_create_private", create)
    monkeypatch.setattr(_private_file, "_windows_dacl_sddl", lambda _path: calls["sddl"])
    return calls


def test_a_private_key_is_created_through_the_restricting_call(fake_windows, tmp_path):
    private, public = tmp_path / "private.pem", tmp_path / "public.pem"
    write_new_file(private, b"private", 0o600)
    write_new_file(public, b"public", 0o644)
    assert fake_windows["created"] == [private], "the public half is meant to be read"
    assert private.read_bytes() == b"private"
    assert public.read_bytes() == b"public"


def test_the_per_user_key_file_is_created_the_same_way(fake_windows, tmp_path):
    path = tmp_path / "home" / "key"
    assert load_or_create_key_file(path, lambda: b"k" * 32, 32) == b"k" * 32
    assert fake_windows["created"] == [path]
    assert load_or_create_key_file(path, lambda: b"z" * 32, 32) == b"k" * 32
    assert fake_windows["created"] == [path], "an existing key is read, not recreated"


def test_an_existing_private_key_is_still_never_replaced(fake_windows, tmp_path, monkeypatch):
    private = tmp_path / "private.pem"
    private.write_bytes(b"first")
    with pytest.raises(AutoControlException, match="already exists"):
        write_new_file(private, b"second", 0o600)
    assert private.read_bytes() == b"first"

    def refuse(path):
        raise FileExistsError(str(path))
    monkeypatch.setattr(_private_file, "_windows_create_private", refuse)
    with pytest.raises(AutoControlException, match="already exists"):
        write_new_file(tmp_path / "other.pem", b"x", 0o600)


def test_when_the_access_list_cannot_be_set_the_key_is_created_and_it_is_said(
        fake_windows, tmp_path, monkeypatch, warnings):
    def unsupported(_path):
        raise OSError(50, "The request is not supported")
    monkeypatch.setattr(_private_file, "_windows_create_private", unsupported)
    private = tmp_path / "private.pem"
    write_new_file(private, b"private", 0o600)
    assert private.read_bytes() == b"private"
    assert len(warnings()) == 1
    assert "could not restrict" in warnings()[0]


def test_loading_a_key_others_can_read_warns_once(fake_windows, tmp_path, warnings):
    path = tmp_path / "private.pem"
    path.write_bytes(b"x")
    fake_windows["sddl"] = f"D:AI(A;ID;FA;;;{_USER})(A;ID;0x1200a9;;;BU)(A;ID;FR;;;AU)"
    assert exposure(path) == ["Users", "Authenticated Users"]
    for _load in range(5):
        assert warn_if_exposed(path, "the private signing key") == ["Users", "Authenticated Users"]
    assert len(warnings()) == 1
    assert "Users, Authenticated Users" in warnings()[0]
    assert "icacls" in warnings()[0]


def test_loading_a_key_only_its_owner_can_read_says_nothing(fake_windows, tmp_path, warnings):
    path = tmp_path / "private.pem"
    path.write_bytes(b"x")
    assert warn_if_exposed(path, "the private signing key") == []
    assert warnings() == []


def test_a_key_that_cannot_be_inspected_is_not_reported(fake_windows, tmp_path, monkeypatch,
                                                        warnings):
    def broken(_path):
        raise OSError(5, "Access is denied")
    monkeypatch.setattr(_private_file, "_windows_dacl_sddl", broken)
    assert warn_if_exposed(tmp_path / "private.pem", "the private signing key") == []
    assert warnings() == []


def test_the_signer_warns_about_an_exposed_private_key_and_still_signs(
        fake_windows, tmp_path, warnings):
    pytest.importorskip("cryptography", exc_type=ImportError)
    from je_auto_control.utils.action_signing import (
        create_signing_keypair, sign_action_file, verify_action_file,
    )
    private, public = tmp_path / "private.pem", tmp_path / "public.pem"
    create_signing_keypair(private, public)
    assert fake_windows["created"] == [private]
    flow = tmp_path / "flow.json"
    flow.write_text("[]", encoding="utf-8")
    fake_windows["sddl"] = "D:(A;;FA;;;BA)(A;;FR;;;WD)"
    sign_action_file(flow, private_key_path=private)
    sign_action_file(flow, private_key_path=private)
    assert verify_action_file(flow, public_key_path=public).verified
    exposed = [line for line in warnings() if "readable by Everyone" in line]
    assert len(exposed) == 1
    assert "private signing key" in exposed[0]


def test_key_file_module_uses_the_shared_helper():
    assert _key_file.open_new_private_file is open_new_private_file


# --- the real platform -------------------------------------------------------------------------

def _names_only(dacl_user: str, user: str) -> bool:
    """Whether an SDDL trustee is ``user``: Windows abbreviates well-known SIDs.

    The built-in Administrator (RID 500, the account of a hosted CI runner) is
    printed as ``LA`` rather than as its SID.
    """
    return dacl_user == user or (dacl_user == "LA" and user.endswith("-500"))


@windows_only
def test_a_new_private_file_has_a_protected_list_naming_this_user_only(tmp_path):
    path = tmp_path / "private.pem"
    descriptor = open_new_private_file(path)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(b"key material")
    assert path.read_bytes() == b"key material", "the owner reads and writes it"
    sddl = _private_file._windows_dacl_sddl(path)
    user = _private_file._current_user_sid()
    assert user.startswith("S-1-5-")
    _owner, _sep, dacl = sddl.partition("D:")
    assert dacl.startswith("P"), "protected: nothing is inherited from the directory"
    assert dacl.count("(") == 1
    assert dacl.startswith("P(A;;FA;;;")
    assert dacl.endswith(")")
    assert _names_only(dacl[len("P(A;;FA;;;"):-1], user)
    assert exposure(path) == []


@windows_only
def test_creation_is_exclusive_on_windows(tmp_path):
    path = tmp_path / "private.pem"
    os.close(open_new_private_file(path))
    with pytest.raises(FileExistsError):
        open_new_private_file(path)


@windows_only
def test_a_created_signing_key_is_restricted_and_its_public_half_is_not(tmp_path):
    pytest.importorskip("cryptography", exc_type=ImportError)
    from je_auto_control.utils.action_signing import create_signing_keypair
    private, public = tmp_path / "private.pem", tmp_path / "public.pem"
    create_signing_keypair(private, public)
    user = _private_file._current_user_sid()
    _owner, _sep, dacl = _private_file._windows_dacl_sddl(private).partition("D:")
    assert dacl.startswith("P(A;;FA;;;")
    assert dacl.count("(") == 1
    assert _names_only(dacl[len("P(A;;FA;;;"):-1], user)
    assert "P(" not in _private_file._windows_dacl_sddl(public), "inherits, as before"
    assert b"PRIVATE KEY" in private.read_bytes()


@windows_only
def test_the_real_reader_reports_a_file_opened_up_to_everyone(tmp_path):
    """Build the exposed case with the same API, no child process."""
    import ctypes

    path = tmp_path / "exposed.pem"
    path.write_bytes(b"x")
    advapi32 = _private_file._dll("advapi32")
    kernel32 = _private_file._dll("kernel32")
    descriptor = ctypes.c_void_p()
    convert = advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32,
                        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    user = _private_file._current_user_sid()
    assert convert(f"D:P(A;;FA;;;{user})(A;;FR;;;WD)", 1, ctypes.byref(descriptor), None)
    try:
        present, defaulted, dacl = ctypes.c_int(), ctypes.c_int(), ctypes.c_void_p()
        advapi32.GetSecurityDescriptorDacl.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_int)]
        assert advapi32.GetSecurityDescriptorDacl(
            descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted))
        advapi32.SetNamedSecurityInfoW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_int, ctypes.c_uint32, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        advapi32.SetNamedSecurityInfoW.restype = ctypes.c_uint32
        protected_dacl = 0x4 | 0x80000000
        assert advapi32.SetNamedSecurityInfoW(
            str(path), 1, protected_dacl, None, None, dacl, None) == 0
    finally:
        _private_file._local_free(kernel32, descriptor)
    assert exposure(path) == ["Everyone"]


@posix_only
def test_posix_exposure_follows_the_mode_bits(tmp_path):
    path = tmp_path / "key"
    os.close(open_new_private_file(path))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert exposure(path) == []
    path.chmod(0o644)
    assert exposure(path) == ["group", "others"]
    path.chmod(0o640)
    assert exposure(path) == ["group"]
