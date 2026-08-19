"""Verify AutoControl's ydotool argv against the events the kernel really gets.

The Wayland image answers the capture half and the EIS image answers libei's
half. Both close by naming the same remaining gap — ydotool, which "needs
/dev/uinput and a seat that consumes it" — and that gap was recorded as
needing a GNOME VM.

It does not need one. A seat is required for an injected event to *arrive
somewhere*, but not for it to be *observed*: ydotoold creates an ordinary
uinput device, the kernel exposes it as ``/dev/input/eventN``, and reading
that node gives back the exact ``input_event`` structs ydotool wrote. No
compositor is involved, so a container with ``/dev/uinput`` and the input
device cgroup can settle every claim this backend makes about the CLI:

  * ``click`` bitmasks — ``0xc0`` / ``0xc1`` / ``0xc2`` really are BTN_LEFT /
    BTN_RIGHT / BTN_MIDDLE, and the split edges ``0x40`` / ``0x80`` really do
    send a press without a release and a release without a press, which is
    the whole basis of :func:`press_mouse` and drag;
  * ``mousemove --absolute`` — what it puts on the wire, which is not what
    the option name suggests;
  * ``mousemove --wheel`` signs — the direction this project assumed from the
    kernel's ``REL_WHEEL`` convention and never measured, plus that the axes
    are not swapped;
  * ``key CODE:STATE`` — numeric evdev codes, both edges.

It also pins the reason :mod:`je_auto_control.linux_wayland._ydotool_cli`
exists: the same argv is replayed against whatever ydotool is installed, and
the legacy 0.1.x CLI answers ``0`` while emitting nothing.

Exit status is the number of failed checks.
"""
from __future__ import annotations

import glob
import os
import struct
import subprocess  # nosec B404  # reason: argv-list, fixed tool names, no shell
import sys
import time
import traceback
from typing import Any, Callable, Dict, List, Optional, Tuple

_results: List[Tuple[str, bool]] = []

#: ``struct input_event``: two ``long`` for the timeval, then type/code/value.
_EVENT_FORMAT = "llHHi"
_EVENT_SIZE = struct.calcsize(_EVENT_FORMAT)

EV_SYN, EV_KEY, EV_REL, EV_ABS = 0x00, 0x01, 0x02, 0x03

BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 272, 273, 274
KEY_A, KEY_LEFTCTRL = 30, 29
REL_X, REL_Y, REL_HWHEEL, REL_WHEEL = 0x00, 0x01, 0x06, 0x08

#: Input event nodes are character major 13, minor 64 + N.
_INPUT_MAJOR = 13
_INPUT_MINOR_BASE = 64

#: ydotoold names its device this; matched case-insensitively.
_DEVICE_NAME_FRAGMENT = "ydotool"

#: Long enough for ydotool's own default 100 ms start delay plus slack.
_SETTLE_SECONDS = 0.45


def check(name: str, fn: Callable[[], Any]) -> Any:
    try:
        detail = fn()
    except Exception:  # noqa: BLE001  # reason: one failed check must not stop the rest
        _results.append((name, False))
        print(f"FAIL  {name}")
        print("        " + traceback.format_exc(limit=4).strip().replace(
            "\n", "\n        "))
        return None
    _results.append((name, True))
    print(f"ok    {name}" + (f"  — {detail}" if detail else ""))
    return detail


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# --------------------------------------------------------------------------
# Reading the virtual device
# --------------------------------------------------------------------------

def _device_names() -> Dict[str, str]:
    """Map ``eventN`` -> device name, straight out of sysfs."""
    names = {}
    for path in glob.glob("/sys/class/input/event*"):
        try:
            with open(os.path.join(path, "device", "name"),
                      encoding="utf-8") as handle:
                names[os.path.basename(path)] = handle.read().strip()
        except OSError:
            continue
    return names


class VirtualDevice:
    """Every ydotoold input node, opened non-blocking and read as a group.

    ydotoold may expose more than one node (a stale daemon from an earlier
    run leaves one behind), and which one carries a given event is not
    something this project should depend on, so they are drained together.
    """

    def __init__(self) -> None:
        self._fds: Dict[str, int] = {}

    def open_all(self) -> List[str]:
        os.makedirs("/dev/input", exist_ok=True)
        opened = []
        for node_name, device_name in _device_names().items():
            if _DEVICE_NAME_FRAGMENT not in device_name.lower():
                continue
            if node_name in self._fds:
                continue
            path = f"/dev/input/{node_name}"
            if not os.path.exists(path):
                minor = _INPUT_MINOR_BASE + int(node_name.replace("event", ""))
                os.mknod(path, 0o600 | 0o020000,
                         os.makedev(_INPUT_MAJOR, minor))
            self._fds[node_name] = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            opened.append(path)
        return opened

    def drain(self) -> List[Tuple[int, int, int]]:
        """Return every pending ``(type, code, value)``, SYN frames dropped."""
        events: List[Tuple[int, int, int]] = []
        for fd in self._fds.values():
            events.extend(self._drain_one(fd))
        return events

    @staticmethod
    def _drain_one(fd: int) -> List[Tuple[int, int, int]]:
        """Read one input node dry.

        One OSError branch covers both endings: BlockingIOError is a subclass
        of it and means nothing more is queued, and anything else means the
        node went away — either way this descriptor is done for now.
        """
        events: List[Tuple[int, int, int]] = []
        while True:
            try:
                data = os.read(fd, _EVENT_SIZE)
            except OSError:
                break
            if not data or len(data) < _EVENT_SIZE:
                break
            _, _, etype, code, value = struct.unpack(_EVENT_FORMAT, data)
            if etype != EV_SYN:
                events.append((etype, code, value))
        return events

    def close(self) -> None:
        for fd in self._fds.values():
            try:
                os.close(fd)
            except OSError:
                pass
        self._fds.clear()


def _emit(device: VirtualDevice, argv: List[str],
          ) -> Tuple[int, str, List[Tuple[int, int, int]]]:
    """Run one ydotool command and return ``(rc, stderr, events)``."""
    device.drain()
    completed = subprocess.run(  # nosec B603  # nosemgrep
        argv, capture_output=True, timeout=20, check=False,
    )
    time.sleep(_SETTLE_SECONDS)
    stderr = completed.stderr.decode("utf-8", errors="replace").strip()
    return completed.returncode, stderr, device.drain()


def _keys(events: List[Tuple[int, int, int]]) -> List[Tuple[int, int]]:
    return [(code, value) for etype, code, value in events if etype == EV_KEY]


def _rel(events: List[Tuple[int, int, int]]) -> List[Tuple[int, int]]:
    return [(code, value) for etype, code, value in events if etype == EV_REL]


# --------------------------------------------------------------------------
# The checks
# --------------------------------------------------------------------------

def _button_check(device: VirtualDevice, tool: str, code: str,
                  expected: List[Tuple[int, int]]) -> str:
    rc, stderr, events = _emit(device, [tool, "click", code])
    _require(rc == 0, f"ydotool click {code} exited {rc}: {stderr}")
    seen = _keys(events)
    _require(seen == expected,
             f"click {code} produced {seen}, expected {expected}")
    return f"{code} -> {seen}"


def _wheel_check(device: VirtualDevice, tool: str, delta_x: int, delta_y: int,
                 expected: List[Tuple[int, int]]) -> str:
    rc, stderr, events = _emit(device, [
        tool, "mousemove", "--wheel", "-x", str(delta_x), "-y", str(delta_y)])
    _require(rc == 0, f"ydotool mousemove --wheel exited {rc}: {stderr}")
    seen = [pair for pair in _rel(events)
            if pair[0] in (REL_WHEEL, REL_HWHEEL)]
    _require(seen == expected,
             f"wheel ({delta_x}, {delta_y}) produced {seen}, "
             f"expected {expected}")
    return f"(-x {delta_x} -y {delta_y}) -> {seen}"


def _absolute_move_check(device: VirtualDevice, tool: str) -> str:
    """``--absolute`` is relative-with-a-reset, and that is worth pinning.

    ydotool 1.x has no ABS axes on its device. It fakes an absolute move by
    sending ``INT32_MIN`` on both axes first — which every compositor clamps
    to the top-left corner — and then the target coordinates as a relative
    delta from there. So AutoControl's ``set_position`` lands on the pixel it
    asked for only because of that clamp, and the reset pair has to be
    present: without it the move would be relative to wherever the cursor
    already was.
    """
    target_x, target_y = 640, 400
    rc, stderr, events = _emit(device, [
        tool, "mousemove", "--absolute",
        "-x", str(target_x), "-y", str(target_y)])
    _require(rc == 0, f"ydotool mousemove --absolute exited {rc}: {stderr}")
    moves = _rel(events)
    _require(len(moves) == 4,
             f"expected a reset pair then the target pair, got {moves}")
    reset_x, reset_y, move_x, move_y = moves
    int32_min = -(2 ** 31)
    _require(reset_x == (REL_X, int32_min) and reset_y == (REL_Y, int32_min),
             f"expected an INT32_MIN reset on both axes, got "
             f"{reset_x}, {reset_y}")
    _require(move_x == (REL_X, target_x) and move_y == (REL_Y, target_y),
             f"expected the target as a relative delta, got {move_x}, {move_y}")
    return "reset to origin, then REL_X 640 / REL_Y 400"


def _key_check(device: VirtualDevice, tool: str) -> str:
    rc, stderr, events = _emit(device, [tool, "key", "30:1", "30:0"])
    _require(rc == 0, f"ydotool key exited {rc}: {stderr}")
    seen = _keys(events)
    _require(seen == [(KEY_A, 1), (KEY_A, 0)],
             f"key 30:1 30:0 produced {seen}")
    return f"30:1 30:0 -> {seen}"


def _backend_argv_check(device: VirtualDevice) -> str:
    """Drive the real backend functions, not a hand-written argv.

    Everything above proves what ydotool does with a given command line. This
    proves AutoControl builds that command line — the two halves are only
    worth something together.
    """
    os.environ["JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND"] = "cli"
    from je_auto_control.linux_wayland import keyboard, mouse

    device.drain()
    mouse.click_mouse(mouse.wayland_mouse_right)
    time.sleep(_SETTLE_SECONDS)
    _require(_keys(device.drain()) == [(BTN_RIGHT, 1), (BTN_RIGHT, 0)],
             "mouse.click_mouse(right) did not reach the kernel as BTN_RIGHT")

    device.drain()
    mouse.press_mouse(mouse.wayland_mouse_left)
    time.sleep(_SETTLE_SECONDS)
    _require(_keys(device.drain()) == [(BTN_LEFT, 1)],
             "mouse.press_mouse(left) sent something other than a lone press")
    mouse.release_mouse(mouse.wayland_mouse_left)
    time.sleep(_SETTLE_SECONDS)
    _require(_keys(device.drain()) == [(BTN_LEFT, 0)],
             "mouse.release_mouse(left) sent something other than a lone "
             "release")

    device.drain()
    mouse.scroll(1, mouse.wayland_scroll_direction_up)
    time.sleep(_SETTLE_SECONDS)
    _require(_rel(device.drain()) == [(REL_WHEEL, 1)],
             "mouse.scroll(up) did not reach the kernel as REL_WHEEL +1")

    device.drain()
    keyboard.hotkey([KEY_LEFTCTRL, KEY_A])
    time.sleep(_SETTLE_SECONDS)
    _require(_keys(device.drain()) == [
        (KEY_LEFTCTRL, 1), (KEY_A, 1), (KEY_A, 0), (KEY_LEFTCTRL, 0)],
        "keyboard.hotkey did not press in order and release in reverse")
    return "click / press / release / scroll / hotkey all land as intended"


def _legacy_cli_detection_check(tool: str) -> str:
    """The installed CLI must be classified as the modern one.

    This is the sentinel for :mod:`_ydotool_cli`: if a future ydotool changes
    its usage banner, the probe starts answering ``unknown``, the guard stops
    protecting anyone, and this check is what says so.
    """
    from je_auto_control.linux_wayland import _ydotool_cli

    _ydotool_cli.reset_cache()
    generation = _ydotool_cli.cli_generation(tool)
    _require(generation == _ydotool_cli.MODERN,
             f"the probe classified this ydotool as {generation!r}, not "
             f"{_ydotool_cli.MODERN!r}; the 0.1.x guard is now blind")
    _require(_ydotool_cli.reject_legacy_cli(tool) == tool,
             "reject_legacy_cli refused a modern ydotool")
    return generation


def _start_daemon() -> subprocess.Popen:
    # Debian's ydotoold binds $XDG_RUNTIME_DIR/.ydotool_socket, and creates
    # neither the directory nor a fallback: without it the daemon still comes
    # up and still creates the uinput device, but every client exits 2 with an
    # empty stderr. Upstream's default is /tmp/.ydotool_socket, so which path
    # is in use is a packaging detail — making the directory is what keeps
    # both working.
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        os.makedirs(runtime_dir, mode=0o700, exist_ok=True)
        os.chmod(runtime_dir, 0o700)
    daemon = subprocess.Popen(  # nosec B603 B607  # nosemgrep
        ["ydotoold"], stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if any(_DEVICE_NAME_FRAGMENT in name.lower()
               for name in _device_names().values()):
            time.sleep(0.5)  # let the node settle before the first read
            return daemon
        if daemon.poll() is not None:
            raise RuntimeError(f"ydotoold exited {daemon.returncode}")
        time.sleep(0.1)
    raise RuntimeError("ydotoold created no input device within 15s")


def _tool_path() -> str:
    from je_auto_control.linux_wayland._detect import binary_path
    path = binary_path("ydotool")
    if path is None:
        raise RuntimeError("ydotool is not on PATH")
    return path


def main() -> int:
    print("AutoControl ydotool verification — real /dev/uinput, no compositor")
    print("=" * 70)

    if not os.path.exists("/dev/uinput"):
        print("FAIL  /dev/uinput is missing. Run the container with "
              "--device /dev/uinput (and `modprobe uinput evdev` on the host).")
        return 1

    tool = _tool_path()
    daemon: Optional[subprocess.Popen] = None
    device = VirtualDevice()
    try:
        daemon = _start_daemon()
        nodes = device.open_all()
        if not nodes:
            print("FAIL  ydotoold's device has no evdev node. The host kernel "
                  "needs the evdev handler (`modprobe evdev`), and the "
                  "container needs --device-cgroup-rule 'c 13:* rmw'.")
            return 1
        print(f"reading {', '.join(nodes)}\n")

        check("click 0xc0 is BTN_LEFT down then up",
              lambda: _button_check(device, tool, "0xc0",
                                    [(BTN_LEFT, 1), (BTN_LEFT, 0)]))
        check("click 0x40 is a press with no release",
              lambda: _button_check(device, tool, "0x40", [(BTN_LEFT, 1)]))
        check("click 0x80 is a release with no press",
              lambda: _button_check(device, tool, "0x80", [(BTN_LEFT, 0)]))
        check("click 0xc1 is BTN_RIGHT",
              lambda: _button_check(device, tool, "0xc1",
                                    [(BTN_RIGHT, 1), (BTN_RIGHT, 0)]))
        check("click 0xc2 is BTN_MIDDLE",
              lambda: _button_check(device, tool, "0xc2",
                                    [(BTN_MIDDLE, 1), (BTN_MIDDLE, 0)]))
        check("mousemove --absolute resets to the origin first",
              lambda: _absolute_move_check(device, tool))
        check("wheel +y is REL_WHEEL positive (up, per the kernel convention)",
              lambda: _wheel_check(device, tool, 0, 1, [(REL_WHEEL, 1)]))
        check("wheel -y is REL_WHEEL negative (down)",
              lambda: _wheel_check(device, tool, 0, -1, [(REL_WHEEL, -1)]))
        check("wheel +x is REL_HWHEEL positive (right), axes not swapped",
              lambda: _wheel_check(device, tool, 2, 0, [(REL_HWHEEL, 2)]))
        check("key CODE:STATE sends numeric evdev codes",
              lambda: _key_check(device, tool))
        check("the version probe recognises this CLI as modern",
              lambda: _legacy_cli_detection_check(tool))
        check("the backend's own argv lands as intended",
              lambda: _backend_argv_check(device))
    finally:
        device.close()
        if daemon is not None:
            daemon.terminate()
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()

    failed = [name for name, ok in _results if not ok]
    print("\n" + "=" * 70)
    print(f"{len(_results) - len(failed)}/{len(_results)} checks passed")
    for name in failed:
        print(f"  failed: {name}")
    return len(failed)


if __name__ == "__main__":
    sys.exit(main())
