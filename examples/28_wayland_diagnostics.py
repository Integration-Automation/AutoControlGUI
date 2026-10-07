"""Report passive capability metadata; never request portal consent or send input."""
# pylint: disable=invalid-name  # reason: numbered example filenames follow the repository catalog
import argparse
import json

import je_auto_control as ac


def main() -> None:
    """Print host metadata without claiming native acceptance."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--display-server', choices=('auto', 'x11', 'wayland'), default='auto')
    args = parser.parse_args()
    context = ac.BackendContext(display_server=args.display_server)
    print(json.dumps({'validated': True, 'platform': context.platform,
                      'capabilities': ac.probe_capabilities(context).to_dict(),
                      'native_operations': [], 'note': 'Metadata does not prove native authorization.'}))


if __name__ == '__main__':
    main()
