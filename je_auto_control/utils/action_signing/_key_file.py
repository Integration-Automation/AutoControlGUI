"""Create and read the per-user key files behind action signing and encryption.

The file is created with ``O_CREAT | O_EXCL`` and mode 0600 in one call, so it
is never readable by others between creation and ``chmod``, and two processes
racing to create it cannot both write a key: the loser reads the winner's. A
key file shorter than ``min_length`` is refused -- an empty file left by a
crash would otherwise become an empty HMAC key that anyone can reproduce.

Mode bits mean nothing on Windows, where the same call left the key with its
directory's access list; there the file is created with an access list naming
the current user only (:mod:`._private_file`). A key that others can read is
reported when it is loaded.
"""
import os
import time
from pathlib import Path
from typing import Callable

from je_auto_control.utils.action_signing._private_file import (
    open_new_private_file, warn_if_exposed,
)
from je_auto_control.utils.exception.exceptions import AutoControlException


def _read_when_written(path: Path, min_length: int) -> bytes:
    """Read the key, waiting briefly for a concurrent creator to finish writing.

    A process that lost the O_EXCL race read the file at once, often empty,
    and was told to delete it -- which would invalidate the winner's key.
    """
    deadline = time.monotonic() + _CREATOR_WAIT_S
    key = path.read_bytes()
    while len(key) < min_length and time.monotonic() < deadline:
        time.sleep(0.02)
        key = path.read_bytes()
    return key


_CREATOR_WAIT_S = 2.0


def load_or_create_key_file(path: Path, generate: Callable[[], bytes],
                            min_length: int) -> bytes:
    """Return the key stored at ``path``, creating it with ``generate()`` first.

    Raises :class:`AutoControlException` when the stored key is shorter than
    ``min_length`` bytes.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = open_new_private_file(path)
        except FileExistsError:
            pass  # another process created it first; read theirs below
        else:
            with os.fdopen(descriptor, "wb") as key_file:
                key_file.write(generate())
    key = _read_when_written(path, min_length)
    if len(key) < min_length:
        raise AutoControlException(
            f"key file {str(path)!r} holds {len(key)} bytes, fewer than {min_length}; "
            "delete it to generate a new key (files signed or encrypted with it "
            "must then be signed or encrypted again)",
        )
    warn_if_exposed(path, "the key file")
    return key


def write_new_file(path: Path, data: bytes, mode: int) -> None:
    """Write ``data`` to a file that must not exist yet, created with ``mode``.

    ``O_EXCL`` makes the refusal atomic, so a key already at ``path`` -- the
    public key an endpoint trusts, say -- can never be replaced through here.
    A ``mode`` that grants nothing to group or others (0600) also restricts
    the file to the current user on Windows. Raises
    :class:`AutoControlException` when ``path`` exists.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if mode & 0o077:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        else:
            descriptor = open_new_private_file(path)
    except FileExistsError as error:
        raise AutoControlException(f"key file {str(path)!r} already exists") from error
    with os.fdopen(descriptor, "wb") as key_file:
        key_file.write(data)
