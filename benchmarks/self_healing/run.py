"""Compare self-healing locator versions on the fixed synthetic dataset.

    python benchmarks/self_healing/run.py                 # text report
    python benchmarks/self_healing/run.py --json out.json # also write JSON
    python benchmarks/self_healing/run.py --check         # exit 1 on a threshold miss

The frames are drawn in memory from ``dataset.json`` (see ``synthetic.py``);
no screen is captured and no pointer or key event is sent. The dataset covers
a plain hit, 125% / 150% display scale, a negative-origin monitor, a region
that has to pick the second of two identical targets, a redesigned control, an
absent target, a look-alike neighbour and one unlabelled frame.

Counts are deterministic. Latency is whatever this machine measured and is
reported, never gated.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
for _entry in (str(_HERE), str(_REPO)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import synthetic  # noqa: E402  # reason: needs the sys.path entry added above

from je_auto_control.utils.self_healing.eval_strategies import (  # noqa: E402  # reason: as above
    build_strategy, comparison_payload,
)
from je_auto_control.utils.self_healing.evaluation import (  # noqa: E402  # reason: as above
    HealingComparison, evaluate_locators, format_comparison,
)


def run() -> HealingComparison:
    """Evaluate every version in ``dataset.json`` on the same drawn frames."""
    descriptor = synthetic.load_descriptor()
    samples = synthetic.build_samples(descriptor)
    versions = {name: build_strategy(config)
                for name, config in descriptor["versions"].items()}
    return evaluate_locators(samples, versions)


def report() -> Dict[str, Any]:
    """The JSON-safe report: comparison, thresholds, violations, ``passed``."""
    return comparison_payload(run(), synthetic.load_descriptor()["thresholds"])


def main(argv: Optional[List[str]] = None) -> int:
    """Command-line entry; returns the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", metavar="PATH", help="write the report as JSON")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when a version misses its thresholds")
    args = parser.parse_args(argv)
    comparison = run()
    payload = comparison_payload(comparison, synthetic.load_descriptor()["thresholds"])
    print(format_comparison(comparison))
    for violation in payload["violations"]:
        print(f"THRESHOLD {violation}")
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=2, sort_keys=True),  # NOSONAR pythonsecurity:S8707
                                   encoding="utf-8")
    return 1 if args.check and payload["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
