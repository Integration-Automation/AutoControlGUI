"""Generate a reviewable candidate from a journal; never execute generated code."""
# pylint: disable=invalid-name  # reason: numbered example filenames follow the repository catalog
import argparse
import json
import tempfile
from dataclasses import replace
from pathlib import Path

import je_auto_control as ac


def fixture(path: Path) -> None:
    """Write a disposable successful sleep step with explicit fixture provenance."""
    journal = ac.ActionJournal(path)
    event = ac.ActionEvent('example', 'sleep-step', None, 1, 'AC_sleep', {'seconds': 0},
                           started_at=1, source='controlled fixture', source_index=0)
    journal.append(event)
    journal.append(replace(event, sequence=2, status='ok', finished_at=2))


def main() -> None:
    """Validate a local fixture or read an explicitly supplied existing journal."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--journal', type=Path)
    parser.add_argument('--run-id', default='example')
    parser.add_argument('--target', choices=('python', 'pytest', 'robot'), default='pytest')
    args = parser.parse_args()
    if args.validate and args.journal:
        parser.error('--validate uses a disposable fixture, not --journal')
    with tempfile.TemporaryDirectory(prefix='ac-example-journal-') as folder:
        path = args.journal or Path(folder) / 'events.jsonl'
        if args.journal is None:
            fixture(path)
        candidate = ac.generate_candidate_from_log(path, run_id=args.run_id, target=args.target)
        if args.target != 'robot':
            compile(candidate.code, '<generated-candidate>', 'exec')
        print(json.dumps({'validated': True, 'candidate': candidate.to_dict(), 'native_operations': []}))


if __name__ == '__main__':
    main()
