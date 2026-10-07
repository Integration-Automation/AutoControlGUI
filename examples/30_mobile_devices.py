"""Inspect an owned device passively; capture only with explicit target and output."""
# pylint: disable=invalid-name  # reason: numbered example filenames follow the repository catalog
import argparse
import json
from typing import Any

import je_auto_control as ac


def main() -> None:
    """Use session ownership without creating an SDK client during validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--platform', choices=('android', 'ios'), default='android')
    parser.add_argument('--target')
    parser.add_argument('--capture', help='Explicit output PNG; sends a device capture request')
    args = parser.parse_args()
    if args.capture and (args.validate or not args.target):
        parser.error('--capture requires --target and cannot accompany --validate')
    target = args.target or ('offline-example' if args.platform == 'android' else 'http://127.0.0.1:8100')
    context = ac.DeviceContext(args.platform, 'example-phone', target, timeout_s=30)
    with ac.open_device(context) as session:
        report: dict[str, Any] = {'validated': True,
                                  'setup': ac.inspect_device_setup(session, connect=False).to_dict(),
                                  'matrix': ac.mobile_surface_matrix(), 'native_operations': []}
        if args.capture:
            with session.bind():
                ac.mobile_capture(args.capture)
            report['native_operations'].append('capture')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
