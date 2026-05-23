"""``python -m autocontrol_lsp.server`` entry point."""
import sys

from autocontrol_lsp.server.server import run


if __name__ == "__main__":
    sys.exit(run())
