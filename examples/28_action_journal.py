"""Capture variable-only actions and inspect snapshots without desktop input.

Run: python examples/28_action_journal.py run.jsonl --run-id example
"""
import argparse
import json
from pathlib import Path

from je_auto_control import executor, execution_scope, inspect_journal


def main() -> None:
    """Append one explicitly owned capture and print its sanitized snapshots."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    parser.add_argument("--run-id", default="example")
    args = parser.parse_args()
    actions = [["AC_journal_capture", {
        "path": str(args.journal), "run_id": args.run_id,
        "body": [["AC_set_var", {"name": "message", "value": "hello"}],
                 ["AC_get_var", {"name": "message"}]],
    }]]
    with execution_scope():
        executor.execute_action(actions, raise_on_error=True)
    print(json.dumps(inspect_journal(args.journal, run_id=args.run_id), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
