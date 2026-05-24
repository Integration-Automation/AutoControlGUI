"""Orchestrate a DAG of automation steps across multiple AutoControl hosts.

Local nodes run in-process; remote nodes execute via the admin
console's REST client (so ``host: "machine-a"`` must match a label
previously registered with :class:`AdminConsoleClient`).

Failures cascade — every node whose ancestry contains a failure is
reported as ``skipped`` instead of being attempted, which keeps a
broken upstream from spamming downstream hosts with doomed calls.
"""
import json

from je_auto_control import run_dag


DEFINITION = {
    "nodes": [
        {
            "id": "screenshot_local",
            "host": "local",
            "actions": [
                ["AC_screenshot", {"file_path": "local.png"}],
            ],
        },
        {
            "id": "smoke_remote_alpha",
            "host": "machine-alpha",  # must be registered with the admin console
            "actions": [
                ["AC_screenshot", {"file_path": "alpha.png"}],
            ],
            "depends_on": ["screenshot_local"],
        },
        {
            "id": "smoke_remote_beta",
            "host": "machine-beta",
            "actions": [
                ["AC_screenshot", {"file_path": "beta.png"}],
            ],
            "depends_on": ["screenshot_local"],
        },
        {
            "id": "summary",
            "host": "local",
            "actions": [
                ["AC_screenshot", {"file_path": "after-fanout.png"}],
            ],
            "depends_on": ["smoke_remote_alpha", "smoke_remote_beta"],
        },
    ],
}


def main() -> None:
    result = run_dag(DEFINITION, max_parallel=4)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
