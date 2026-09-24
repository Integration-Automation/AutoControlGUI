"""Create and read the per-user key files behind action signing and encryption.

The file is created with ``O_CREAT | O_EXCL`` and mode 0600 in one call, so it
is never readable by others between creation and ``chmod``, and two processes
racing to create it cannot both write a key: the loser reads the winner's. A
key file shorter than ``min_length`` is refused -- an empty file left by a
crash would otherwise become an empty HMAC key that anyone can reproduce.
"""
import os
import time
from pathlib import Path
from typing import Callable

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
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
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
    return key
