"""JSON command adapter for journal candidates and optional explicit ZIP exports."""
from je_auto_control.utils.codegen.candidate_archive import write_candidate_archive
from je_auto_control.utils.codegen.journal_import import generate_candidate_from_log


def _generate_candidate_command(path: str, run_id: str, target: str = "pytest", style: str = "actions",
                                  output: str | None = None) -> dict[str, object]:
    """Return candidate source/provenance, optionally atomically exporting a ZIP review artifact."""
    candidate = generate_candidate_from_log(path, run_id=run_id, target=target, style=style)
    data = candidate.to_dict()
    if output is not None:
        data["output"] = str(write_candidate_archive(candidate, output))
    return data
