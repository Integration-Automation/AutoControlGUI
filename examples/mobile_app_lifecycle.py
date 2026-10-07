"""Passively inspect app capabilities; --run explicitly opts into native app input."""
import argparse
import json
from dataclasses import asdict

from je_auto_control.api.mobile import DeviceContext, launch_app, open_device, stop_app


def main() -> None:
    """Keep the default example hardware-free; select one exact native target to run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=('android', 'ios'), default='android')
    parser.add_argument('--target', default='emulator-5554')
    parser.add_argument('--app-id', default='com.example.demo')
    parser.add_argument('--run', action='store_true', help='explicitly launch and stop the selected app')
    args = parser.parse_args()
    target = args.target if args.platform == 'android' else (
        'http://127.0.0.1:8100' if args.target == 'emulator-5554' else args.target)
    with open_device(DeviceContext(args.platform, 'example-phone', target=target, timeout_s=10)) as session:
        print(json.dumps({key: asdict(value) for key, value in session.capabilities.items()}, indent=2))
        if args.run:
            print(asdict(launch_app(session, args.app_id)))
            print(asdict(stop_app(session, args.app_id)))


if __name__ == '__main__':
    main()
