"""``python -m je_auto_control.utils.action_lint`` entry point."""
import sys

from je_auto_control.utils.action_lint.linter import _main


if __name__ == "__main__":
    sys.exit(_main())
