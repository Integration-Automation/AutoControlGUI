"""Passive setup by default; explicit flags opt into connectivity and native app/capture smoke."""
import argparse
import json
from dataclasses import asdict

from je_auto_control.api.mobile import (
    DeviceContext, inspect_device_setup, launch_app, mobile_capture, open_device, stop_app,
)


def main() -> None:
    """Produce evidence only for exercised operations on one explicitly selected device."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', choices=('android', 'ios'), default='android')
    parser.add_argument('--target')
    parser.add_argument('--adb-path')
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--validate', action='store_true', help='force passive metadata only')
    parser.add_argument('--connect', action='store_true', help='explicit get-state / WDA GET status')
    parser.add_argument('--exercise', action='store_true', help='explicit native app launch, frame capture and stop')
    parser.add_argument('--app-id', help='required for exercise; choose an installed disposable test app')
    parser.add_argument('--output', default='mobile-smoke.png')
    args = parser.parse_args()
    if args.validate and (args.connect or args.exercise):
        parser.error('--validate cannot perform native operations')
    if args.exercise and (not args.connect or not args.app_id):
        parser.error('--exercise requires --connect and --app-id')
    target = args.target or ('emulator-5554' if args.platform == 'android' else 'http://127.0.0.1:8100')
    context = DeviceContext(args.platform, 'smoke-phone', target=target, adb_path=args.adb_path,
                            timeout_s=args.timeout)
    with open_device(context) as session:
        report = {'platform': args.platform, 'setup': inspect_device_setup(session, connect=args.connect).to_dict(),
                  'actual': [], 'skipped': ['Unicode focus round-trip, rotation and IME restoration not exercised']}
        if args.connect:
            report['actual'].append('authorization/status')
        if args.exercise:
            report['launch'] = asdict(launch_app(session, args.app_id))
            try:
                with session.bind():
                    report['frame'] = mobile_capture(args.output)
                report['actual'].extend(['observed launch', 'device frame capture'])
            finally:
                report['stop'] = asdict(stop_app(session, args.app_id))
            report['actual'].append('observed stop')
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
