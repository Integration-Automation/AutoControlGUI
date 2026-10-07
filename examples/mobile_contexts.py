"""Passively inspect two configured devices and run a hardware-free matrix."""
import json

from je_auto_control.api.mobile import DeviceContext, open_device, probe_device_contexts
from je_auto_control.utils.device_matrix import run_on_devices


def main() -> None:
    """No SDK import, ADB scan, network connection or device input is requested."""
    devices = [
        {'platform': 'android', 'serial': 'emulator-5554', 'timeout_s': 5},
        {'platform': 'ios', 'device_id': 'remote-iphone', 'url': 'http://127.0.0.1:8100', 'timeout_s': 5},
    ]
    print(json.dumps(probe_device_contexts(devices), indent=2))
    with open_device(DeviceContext.from_spec(devices[0])) as session:
        with session.bind():
            print(session.context.device_id, session.connected)
        # Inside bind(), existing Android/iOS helpers use this owner implicitly.
        # A real operation requires the selected device and optional SDK setup.
    report = run_on_devices([['AC_set_var', {'name': 'current', 'value': '${device.platform}'}]], devices)
    print(json.dumps(report.to_dict(), indent=2))


if __name__ == '__main__':
    main()
