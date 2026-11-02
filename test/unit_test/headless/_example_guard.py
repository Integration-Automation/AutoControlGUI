"""Run a script with every way of touching a device replaced by a tripwire.

``python _example_guard.py SCRIPT [ARGS...]`` runs ``SCRIPT`` as ``__main__``
after replacing:

* the platform backend's keyboard, mouse, screen and recorder functions;
* ``PIL.ImageGrab.grab`` (the capture path that is not a backend function);
* ``subprocess.Popen`` -- no ``adb``, ``ydotool``, ``grim`` or anything else;
* socket connections to anything that is not this machine.

A tripped wire is written to the file named by ``AC_EXAMPLE_GUARD_EFFECTS``
*and* raised. The file is what a test reads: a script that swallowed the
exception would otherwise look clean.

This is what lets a test say an example's ``--validate`` path has no device
effect, instead of trusting that it was written carefully.
"""
import json
import os
import runpy
import socket
import subprocess  # nosec B404  # reason: patched below so that nothing can be spawned
import sys
import types
from typing import Any, Callable, List

EFFECTS_ENV = "AC_EXAMPLE_GUARD_EFFECTS"
_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})
_BACKEND_MODULES = ("keyboard", "mouse", "screen", "keyboard_check", "_keyboard", "_mouse")
_effects: List[str] = []


class DeviceEffect(RuntimeError):
    """Something tried to act outside the process."""


def record(kind: str, detail: Any) -> None:
    """Note one effect and persist the list, so it survives a swallowed exception."""
    _effects.append(f"{kind}: {detail}")
    path = os.environ.get(EFFECTS_ENV)
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(_effects, handle)


def effects() -> List[str]:
    """Every effect recorded in this process."""
    return list(_effects)


def _tripwire(kind: str, name: str) -> Callable[..., Any]:
    def tripped(*_args: Any, **_kwargs: Any) -> Any:
        record(kind, name)
        raise DeviceEffect(f"{kind}: {name}")
    return tripped


def tripwire_module(module: types.ModuleType, kind: str = "backend") -> int:
    """Replace every function ``module`` defines; return how many were replaced."""
    replaced = 0
    for name, value in list(vars(module).items()):
        if isinstance(value, types.FunctionType) and value.__module__ == module.__name__:
            setattr(module, name, _tripwire(kind, f"{module.__name__}.{name}"))
            replaced += 1
    return replaced


class _TrippedObject:
    """Stands in for a backend object: any use of it is an effect."""

    def __init__(self, name: str) -> None:
        self._name = name

    def __getattr__(self, attribute: str) -> Any:
        return _tripwire("backend", f"{self._name}.{attribute}")


def _is_loopback(address: Any) -> bool:
    return isinstance(address, tuple) and bool(address) and str(address[0]) in _LOOPBACK


def _guard_network() -> None:
    real_connect = socket.socket.connect

    def connect(self: socket.socket, address: Any) -> Any:
        if not _is_loopback(address):
            record("network", address)
            raise DeviceEffect(f"network: {address!r}")
        return real_connect(self, address)

    socket.socket.connect = connect  # type: ignore[method-assign]
    socket.socket.connect_ex = connect  # type: ignore[method-assign]


def _guard_processes() -> None:
    def refuse(_self: Any, args: Any = None, *_rest: Any, **_options: Any) -> None:
        record("process", args)
        raise DeviceEffect(f"process: {args!r}")

    subprocess.Popen.__init__ = refuse  # type: ignore[method-assign]


def _guard_backends() -> None:
    try:
        from je_auto_control.wrapper import platform_wrapper
    except Exception:  # noqa: BLE001  # reason: no backend loaded means none to guard; the script reports its own import failure
        return
    for attribute in _BACKEND_MODULES:
        module = getattr(platform_wrapper, attribute, None)
        if isinstance(module, types.ModuleType):
            tripwire_module(module)
    if getattr(platform_wrapper, "recorder", None) is not None:
        platform_wrapper.recorder = _TrippedObject("recorder")
    try:
        from PIL import ImageGrab
    except ImportError:
        return
    ImageGrab.grab = _tripwire("capture", "PIL.ImageGrab.grab")


def install() -> None:
    """Install every tripwire in this process."""
    _guard_backends()
    _guard_processes()
    _guard_network()


def main(argv: List[str]) -> None:
    """Install the tripwires, then run ``argv[0]`` as ``__main__`` with the rest as its argv."""
    if not argv:
        raise SystemExit("usage: _example_guard.py SCRIPT [ARGS...]")
    record_path = os.environ.get(EFFECTS_ENV)
    if record_path:
        with open(record_path, "w", encoding="utf-8") as handle:
            json.dump([], handle)
    install()
    sys.argv = list(argv)
    runpy.run_path(argv[0], run_name="__main__")


if __name__ == "__main__":
    main(sys.argv[1:])
