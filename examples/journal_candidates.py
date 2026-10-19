"""Generate and archive synthetic journal candidates without replaying device input."""
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from je_auto_control import ActionEvent, ActionJournal, generate_candidate_from_log, write_candidate_archive


def main() -> None:
    """Use temporary files and declared observations; no native command or model runs."""
    with TemporaryDirectory(prefix="autocontrol-journal-candidate-") as directory:
        root = Path(directory)
        journal = ActionJournal(root / "synthetic.jsonl")
        event = ActionEvent("synthetic-run", "step", "AC_set_var", {"name": "sample", "value": 42}, 1.0)
        journal.append(event)
        journal.append(replace(event, status="ok", finished_at=2.0))
        summaries = []
        for target in ("pytest", "python", "robot"):
            candidate = generate_candidate_from_log(journal.path, run_id="synthetic-run", target=target)
            archive = write_candidate_archive(candidate, root / f"{target}-review.zip")
            if not archive.is_file() or candidate.actions != [["AC_set_var", {"name": "sample", "value": 42}]]:
                raise RuntimeError("synthetic candidate evidence did not match")
            summaries.append({"target": target, "observed_path_only": candidate.observed_path_only,
                              "validation": candidate.manifest["validation"], "archive": archive.name})
        print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
