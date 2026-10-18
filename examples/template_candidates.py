"""Run a local candidate preview/verify/accept/revert cycle using synthetic fixture files.

From the repository root: python -m examples.template_candidates
No capture, input, network backend or user template is used.
"""
import json
import tempfile
from pathlib import Path

from je_auto_control import (
    accept_template_candidate, create_template_candidate, preview_template_candidate,
    revert_template_candidate, verify_template_candidate,
)


def main() -> None:
    """Keep the whole demonstration inside its own temporary directory."""
    fixtures = Path(__file__).resolve().parents[1] / "benchmarks/self_healing/fixtures"
    with tempfile.TemporaryDirectory(prefix="autocontrol-template-candidate-") as temporary:
        folder = Path(temporary)
        target, bundle, dataset = (folder / name for name in ("template.png", "candidate.json", "dataset.json"))
        original = (fixtures / "old.png").read_bytes()
        target.write_bytes(original)
        for name in ("frame_new.png", "absent.png"):
            (folder / name).write_bytes((fixtures / name).read_bytes())
        dataset.write_text(json.dumps({"schema_version": 1, "samples": [
            {"id": "changed", "frame": "frame_new.png", "expected_box": [20, 16, 37, 29]},
            {"id": "negative", "frame": "absent.png", "expected_miss": True},
        ]}), encoding="utf-8")
        created = create_template_candidate(target, (fixtures / "new.png").read_bytes(), bundle, threshold=0.99)
        preview = preview_template_candidate(bundle)
        verified = verify_template_candidate(bundle, dataset)
        accepted = accept_template_candidate(bundle, dataset, preview.state.revision)
        reverted = revert_template_candidate(bundle, created.revision)
        if target.read_bytes() != original:
            raise RuntimeError("original bytes were not restored")
        print(json.dumps({"eligible": verified.eligible, "threshold": created.threshold,
                          "accepted": accepted.changed, "reverted": reverted.changed,
                          "final_state": reverted.state.state}, indent=2))


if __name__ == "__main__":
    main()
