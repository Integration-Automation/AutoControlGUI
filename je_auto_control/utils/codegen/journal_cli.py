"""CLI journal-to-candidate mode, kept separate from legacy action-file code generation."""
import argparse
import json
import sys

from je_auto_control.utils.codegen.candidate_archive import write_candidate_archive
from je_auto_control.utils.codegen.candidate_models import CandidateGenerationError
from je_auto_control.utils.codegen.journal_import import generate_candidate_from_log
from je_auto_control.utils.rbac.policy import authorize_command


def candidate_codegen(args: argparse.Namespace) -> int:
    """Print the review bundle as JSON and optionally atomically export one ZIP."""
    authorize_command("AC_generate_candidate_from_log")
    if args.script is not None or not args.run_id:
        raise CandidateGenerationError("--from-log requires --run-id and cannot also take an action script")
    if args.failure_bundle or args.name != "recorded_flow":
        raise CandidateGenerationError("--name and --failure-bundle apply to action-file codegen only")
    candidate = generate_candidate_from_log(args.from_log, run_id=args.run_id,
                                             target=args.target, style=args.style or "actions")
    data = candidate.to_dict()
    if args.output:
        data["output"] = str(write_candidate_archive(candidate, args.output))
        sys.stderr.write(f"Wrote candidate review archive to {args.output}\n")
    sys.stdout.write(json.dumps(data, indent=2, ensure_ascii=True) + "\n")
    return 0
