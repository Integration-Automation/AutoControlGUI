"""Shell, clipboard, adb and USB/IP helpers at the edges the audit found.

Fakes and loopback sockets only; the one real child process is this
interpreter, started to test the timeout of a process tree.
"""
import socket
import struct
import subprocess  # nosec B404  # reason: builds fake CompletedProcess results and runs this interpreter
import sys
import time
import types

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlActionException, AutoControlException
from je_auto_control.utils.shell_process import shell_exec

_SECRET = "hunter2-" + "SECRET"


class _Executor:
    def __init__(self):
        self.variables = types.SimpleNamespace(values={})
        self.variables.set = self.variables.values.__setitem__


# --- AC_shell_to_var / AC_shell_command ---------------------------------------------------------

def test_shell_to_var_refuses_cmd_syntax_in_a_batch_files_arguments(monkeypatch):
    from je_auto_control.utils.executor.flow_data_commands import exec_shell_to_var
    monkeypatch.setattr(shell_exec.sys, "platform", "win32")
    monkeypatch.setattr(shell_exec, "run_captured", lambda *a, **k: pytest.fail("must not run"))
    with pytest.raises(ValueError, match="metacharacters"):
        exec_shell_to_var(_Executor(), {"command": ["probe.bat", "x&ver"]})


def test_shell_to_var_needs_a_command():
    from je_auto_control.utils.executor.flow_data_commands import exec_shell_to_var
    with pytest.raises(AutoControlActionException, match="needs 'command'"):
        exec_shell_to_var(_Executor(), {})


def test_a_timeout_ends_the_whole_process_tree():
    grandchild = ("import subprocess, sys; "
                  "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']).wait()")
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        shell_exec.run_captured([sys.executable, "-c", grandchild], timeout_s=1.0)
    assert time.monotonic() - started < 15


def test_mcp_shell_command_keeps_output_it_cannot_decode_strictly():
    from je_auto_control.utils.mcp_server.tools._handlers_system import shell_command
    script = "import sys; sys.stdout.buffer.write(bytes([111, 107, 32, 255, 254]))"
    result = shell_command(f'"{sys.executable}" -c "{script}"', timeout=30)
    assert result["exit_code"] == 0 and result["stdout"].startswith("ok ")


def test_a_command_that_cannot_start_raises_and_logs_no_arguments(monkeypatch):
    logged = []
    monkeypatch.setattr(shell_exec, "autocontrol_logger", types.SimpleNamespace(
        info=lambda *a: logged.append(a), error=lambda *a: logged.append(a),
        warning=lambda *a: logged.append(a)))

    def cannot_start(*args, **kwargs):
        raise FileNotFoundError("no such program")

    monkeypatch.setattr(shell_exec.subprocess, "Popen", cannot_start)
    manager = shell_exec.ShellManager()
    with pytest.raises(AutoControlActionException, match="could not start"):
        manager.exec_shell(["curl", "-H", f"Authorization: Bearer {_SECRET}"])
    assert logged and _SECRET not in repr(logged)


def test_read_file_to_var_drops_a_byte_order_mark(tmp_path):
    from je_auto_control.utils.executor.flow_data_commands import exec_read_file_to_var
    path = tmp_path / "order.txt"
    path.write_bytes(b"\xef\xbb\xbfORD-1234")
    executor = _Executor()
    exec_read_file_to_var(executor, {"path": str(path), "var": "order"})
    assert executor.variables.values["order"] == "ORD-1234"


# --- clipboard ----------------------------------------------------------------------------------

def _completed(returncode, stdout=b"", stderr=b""):
    return subprocess.CompletedProcess(["xclip"], returncode, stdout, stderr)


def test_an_empty_linux_clipboard_is_empty_and_other_failures_are_framework_errors(monkeypatch):
    from je_auto_control.utils.clipboard import clipboard
    monkeypatch.setattr(clipboard, "_linux_cmd", lambda: ["xclip", "-selection", "clipboard"])
    monkeypatch.setattr(clipboard.subprocess, "run",
                        lambda *a, **k: _completed(1, stderr=b"Error: target STRING not available"))
    assert clipboard._linux_get() == ""  # noqa: SLF001
    monkeypatch.setattr(clipboard.subprocess, "run",
                        lambda *a, **k: _completed(1, stderr=b"Error: Can't open display: :0"))
    with pytest.raises(AutoControlException, match="open display"):
        clipboard._linux_get()  # noqa: SLF001

    def hangs(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="xclip", timeout=5)

    monkeypatch.setattr(clipboard.subprocess, "run", hangs)
    with pytest.raises(AutoControlException):
        clipboard._linux_set("x")  # noqa: SLF001


def test_a_single_file_name_starting_with_a_bracket_is_a_path():
    from je_auto_control.utils.executor.action_executor import _coerce_paths
    assert _coerce_paths("[draft] notes.txt") == ["[draft] notes.txt"]
    assert _coerce_paths('["a.txt", "b.txt"]') == ["a.txt", "b.txt"]


# --- adb ----------------------------------------------------------------------------------------

def test_adb_errors_carry_no_arguments_and_no_permissions_is_a_state(monkeypatch):
    from je_auto_control.android import adb_client
    client = adb_client.AdbClient(adb_path="adb")
    monkeypatch.setattr(adb_client.subprocess, "run", lambda *a, **k: _completed(1, stderr=b"error: closed"))
    with pytest.raises(adb_client.AdbError) as error:
        client.shell(f"input text {_SECRET}")
    assert _SECRET not in str(error.value)
    listing = ("List of devices attached\n0123456789ABCDEF\tno permissions (user in plugdev group; "
               "are your udev rules wrong?); see [http://developer.android.com/tools/device.html] "
               "usb:1-1 transport_id:3\n").encode()
    monkeypatch.setattr(adb_client.subprocess, "run", lambda *a, **k: _completed(0, stdout=listing))
    [device] = client.list_devices()
    assert device.state == "no permissions" and device.transport_id == "3"


# --- USB/IP -------------------------------------------------------------------------------------

class _Intf:
    def __init__(self, alternate):
        self.bAlternateSetting = alternate
        self.bInterfaceClass, self.bInterfaceSubClass, self.bInterfaceProtocol = 14, 1, 0


class _Config(list):
    bNumInterfaces = 2
    bConfigurationValue = 1


class _Dev:
    bus, address, speed = 1, 2, 4
    idVendor, idProduct, bcdDevice = 0x046D, 0x0825, 0x0100
    bDeviceClass = bDeviceSubClass = bDeviceProtocol = 0
    bNumConfigurations = 1
    iManufacturer = 1

    def get_active_configuration(self):
        return _Config([_Intf(0), _Intf(0), _Intf(1), _Intf(2)])


def test_the_device_list_holds_one_record_per_interface_and_kernel_speeds(monkeypatch):
    from je_auto_control.utils.usbip.libusb_backend import LibUsbBackend
    core = types.SimpleNamespace(find=lambda find_all: [_Dev()], USBError=OSError)
    util = types.SimpleNamespace(get_string=lambda *a: (_ for _ in ()).throw(NotImplementedError()))
    monkeypatch.setitem(sys.modules, "usb", types.SimpleNamespace(core=core, util=util))
    monkeypatch.setitem(sys.modules, "usb.core", core)
    monkeypatch.setitem(sys.modules, "usb.util", util)
    backend = LibUsbBackend()
    backend._available = True  # noqa: SLF001
    [device] = backend.list_devices()
    assert device.num_interfaces == len(device.interfaces) == 2
    assert device.speed == 5   # libusb SUPER (4) is the kernel's SUPER (5), not WIRELESS


def _device():
    from je_auto_control.utils.usbip.protocol import UsbIpDevice
    return UsbIpDevice(path="/sys/x", busid="1-1", busnum=1, devnum=2, speed=3, vendor_id=1,
                       product_id=2, bcd_device=0, device_class=0, device_subclass=0,
                       device_protocol=0, configuration_value=1, num_configurations=1,
                       num_interfaces=0)


def _recv(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


@pytest.fixture()
def imported(monkeypatch):
    from je_auto_control.utils.usbip import (
        FakeUrbBackend, OP_REQ_IMPORT, PROTOCOL_VERSION, UrbResponse, UsbIpServer,
    )
    from je_auto_control.utils.usbip import server as server_mod
    monkeypatch.setattr(server_mod, "_CLIENT_READ_TIMEOUT_S", 0.3)
    backend = FakeUrbBackend(devices=[_device()])
    backend.script_urb(devid=0x10002, direction=1, ep=1,
                       response=UrbResponse(status=0, actual_length=4, data=b"PONG"))
    server = UsbIpServer(backend, host="127.0.0.1", port=0)
    server.start()
    sock = socket.create_connection(("127.0.0.1", server.port), timeout=5.0)
    sock.sendall(struct.pack("!HHI", PROTOCOL_VERSION, OP_REQ_IMPORT, 0) + b"1-1".ljust(32, b"\x00"))
    _recv(sock, 8 + 312)
    yield sock
    sock.close()
    server.stop()


def _submit(seqnum, packets):
    from je_auto_control.utils.usbip import USBIP_CMD_SUBMIT
    return (struct.pack("!IIIII", USBIP_CMD_SUBMIT, seqnum, 0x10002, 1, 1)
            + struct.pack("!IIiII8s", 0, 4, 0, packets & 0xFFFFFFFF, 0, b"\x00" * 8))


def test_an_attached_device_may_stay_quiet(imported):
    time.sleep(0.8)   # longer than the (shortened) read timeout
    imported.sendall(_submit(7, -1))
    assert _recv(imported, 48 + 4)[-4:] == b"PONG"


def test_an_isochronous_urb_is_refused_and_the_connection_goes_on(imported):
    imported.sendall(_submit(8, 2) + b"\x00" * 32)   # two 16-byte packet descriptors
    reply = _recv(imported, 48)
    status = struct.unpack("!i", reply[20:24])[0]
    assert struct.unpack("!I", reply[4:8])[0] == 8 and status == -95
    imported.sendall(_submit(9, -1))
    assert _recv(imported, 48 + 4)[-4:] == b"PONG"
