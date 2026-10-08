"""Turn a run recorded in the action journal into a candidate script.

The action journal is an opt-in JSONL file (schema version 1) of what the
executor ran: one ``start`` line and one ``end`` line per action, grouped by
``run_id``. :func:`generate_candidate_from_log` reads one run back and builds
a script for a person to review::

    ac.start_action_journal("run.jsonl", run_id="checkout", session="laptop")
    ac.execute_action(actions)
    ac.stop_action_journal()

    candidate = ac.generate_candidate_from_log("run.jsonl", run_id="checkout")
    print(candidate.code)            # pytest by default; target="python" / "robot"
    print(candidate.warnings)        # what a reviewer has to check
    print(candidate.manifest)        # where each emitted step came from

Three things to know before trusting a candidate:

* It is built from the *inputs* the journal recorded, never from outcomes, and
  generating it executes nothing (``manifest["executed"]`` is ``False``).
* A masked secret is not replayable. It comes back as
  ``${journal_redacted_N_M}``, which fails as an unknown variable until you
  replace it; a ``${secrets.NAME}`` reference in the journal is kept as is.
* ``candidate.observed_path_only`` is true when some control flow could not be
  rebuilt and the steps that ran stand in for it. Read ``candidate.warnings``.

The same thing from a shell::

    je_auto_control codegen --from-log run.jsonl --run-id checkout -o test_checkout.py

and from an action file: ``AC_journal_start`` / ``AC_journal_stop`` /
``AC_generate_code_from_journal``.

Run ``--validate`` to see the whole round trip offline: it records a run made
of variable and flow-control commands only (no mouse, keyboard or screen
command), generates the candidate and dry-runs it. Without the flag the script
converts a journal you name and writes nothing unless ``--output`` is given.
"""
import argparse
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import je_auto_control as ac
# The two helpers the CLI uses; the facade exports generate_candidate_from_log only.
from je_auto_control.utils.codegen.journal_import import only_run_id, write_candidate

#: Variable and flow-control commands only: running these touches no device.
_OFFLINE_RUN = [
    ["AC_set_var", {"name": "attempts", "value": 0}],
    ["AC_loop", {"times": 3, "body": [["AC_inc_var", {"name": "attempts"}]]}],
    ["AC_if_var", {"name": "attempts", "op": "eq", "value": 3,
                   "then": [["AC_set_var", {"name": "status", "value": "done"}]],
                   "else": [["AC_set_var", {"name": "status", "value": "short"}]]}],
]


def describe(candidate: ac.CandidateScript) -> None:
    """Print what a reviewer looks at first."""
    manifest = candidate.manifest
    print(f"run {manifest['run_id']}: {manifest['event_count']} journal event(s)"
          f" -> {manifest['action_count']} top-level action(s)")
    print(f"  executed while generating: {manifest['executed']}")
    print(f"  observed path only:        {candidate.observed_path_only}")
    for step in manifest["steps"]:
        print(f"  journal line {step['line']}: {step['command']}"
              f" ({step['mode']}, {step['status']})")
    for warning in candidate.warnings:
        print(f"  ! {warning}")


def validate() -> int:
    """Record an offline run, rebuild it, and dry-run the result."""
    with tempfile.TemporaryDirectory(prefix="ac_journal_") as folder:
        journal = Path(folder) / "run.jsonl"
        started = ac.start_action_journal(journal, run_id="example", session="validate")
        try:
            # The module-level ac.execute_action takes the list only; the options
            # (raise_on_error, dry_run, step_callback) are on the executor object.
            ac.executor.execute_action(_OFFLINE_RUN, raise_on_error=True)
        finally:
            stopped = ac.stop_action_journal()
        print(f"journal {Path(started['path']).name}: {stopped['events']} event(s) recorded")

        runs = ac.list_journal_runs(journal)
        candidate = ac.generate_candidate_from_log(journal, run_id=only_run_id(journal))
        describe(candidate)

        written = write_candidate(candidate, Path(folder) / "test_example.py",
                                  manifest=Path(folder) / "test_example.manifest.json")
        compile(Path(written["output"]).read_text(encoding="utf-8"), written["output"], "exec")
        # The candidate's action list is what the script replays. A dry run
        # resolves every command name and argument without calling anything.
        dry = ac.executor.execute_action(candidate.actions, dry_run=True)

    problems = []
    if [run["run_id"] for run in runs] != ["example"]:
        problems.append(f"expected one run called 'example', got {runs}")
    if candidate.actions != _OFFLINE_RUN:
        problems.append("the rebuilt action list differs from what was executed")
    if candidate.manifest["executed"] or candidate.manifest["outcomes_used_as_input"]:
        problems.append("the manifest says something was executed or an outcome was reused")
    if len(dry) != len(_OFFLINE_RUN):
        problems.append(f"the dry run covered {len(dry)} of {len(_OFFLINE_RUN)} actions")
    for problem in problems:
        print(f"FAILED: {problem}")
    print("validate:", "failed" if problems else "ok")
    return 1 if problems else 0


def convert(journal: str, run_id: Optional[str], target: str, output: Optional[str]) -> int:
    """Build a candidate from a journal on disk; print it or write it."""
    chosen = run_id or only_run_id(journal)
    candidate = ac.generate_candidate_from_log(journal, run_id=chosen, target=target)
    describe(candidate)
    if output:
        written = write_candidate(candidate, output, manifest=f"{output}.manifest.json")
        print(f"wrote {written['output']} and {written['manifest']}")
    else:
        print(candidate.code)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Parse the command line; see the module docstring."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--validate", action="store_true",
                        help="record, convert and dry-run an offline run in a temp directory")
    parser.add_argument("--journal", help="an existing action journal (.jsonl) to convert")
    parser.add_argument("--run-id", help="the run to use (optional when the journal holds one)")
    parser.add_argument("--target", default="pytest", choices=("pytest", "python", "robot"))
    parser.add_argument("--output", help="write the candidate (and its manifest) here")
    args = parser.parse_args(argv)
    if args.validate:
        return validate()
    if not args.journal:
        parser.error("name a journal with --journal, or use --validate")
    return convert(args.journal, args.run_id, args.target, args.output)


if __name__ == "__main__":
    sys.exit(main())
