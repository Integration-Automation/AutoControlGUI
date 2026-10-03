"""Run the fixed offline template benchmark and export JSON plus HTML."""
import argparse
from pathlib import Path

from je_auto_control import compare_healing_versions


def main() -> None:
    """Compare versioned fixtures without capturing or controlling a device."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, help='Output .json path; .html is written beside it')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    compare_healing_versions(str(root / 'dataset.json'), {
        'before': {'template_path': str(root / 'before.png'), 'threshold': 0.99},
        'after': {'template_path': str(root / 'after.png'), 'threshold': 0.99}}, report_path=args.report)


if __name__ == '__main__':
    main()
