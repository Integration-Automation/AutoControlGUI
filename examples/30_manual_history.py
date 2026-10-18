"""Validate or preview a variable-only manual history/journal run."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

import je_auto_control as ac
from je_auto_control.utils.executor.action_schema import validate_actions
from je_auto_control.utils.path_guard.path_guard import validate_path


def main() -> None:
    """Keep the example's database and journal below an explicit output directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--validate", action="store_true", help="validate without writing files")
    parser.add_argument("--dry-run", action="store_true", help="record a preview rather than dispatching actions")
    args = parser.parse_args()
    actions = [["AC_set_var", {"name": "message", "value": "hello"}]]
    validate_actions(actions, ac.executor.known_commands())
    if args.validate:
        print("validated one variable-only action")
        return
    folder = validate_path(args.directory)
    folder.mkdir(parents=True, exist_ok=True)
    store = ac.HistoryStore(folder / "history.sqlite")
    try:
        source = "example.preview" if args.dry_run else "example"
        with ac.manual_history_scope(store=store, source_id=source, script_path=__file__) as owner:
            result = ac.execute_journal_run(actions, folder / "events.jsonl",
                                            options=ac.JournalRunOptions(dry_run=args.dry_run))
        row = store.get_run(owner.run_id)
        print(json.dumps({"history_id": owner.run_id, "status": row.status if row is not None else None,
                          "links": [asdict(link) for link in store.journals_for_run(owner.run_id)],
                          "record": result["record"]}, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
