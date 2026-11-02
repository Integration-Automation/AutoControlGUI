"""Build the owner service and run its unprivileged acceptance with the system C compiler.

Linux only. Usage: python3 run_checks.py
Needs a C11 compiler (``CC``, default ``cc``), glibc headers with ``PIDFD_GET_INFO`` and a
kernel with pidfs (6.13 or later). Nothing is installed and nothing runs as root; the
protected acceptance is ``protected_run.py``, run separately as root. Prints one JSON
object and exits 0 only when every suite gave its expected result.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

TESTS = Path(__file__).resolve().parent
SOURCE = TESTS.parent / "src"
REPOSITORY = TESTS.parents[2]
CC = os.environ.get("CC", "cc")
FLAGS = ["-std=c11", "-pthread", "-Wall", "-Wextra", "-Werror", f"-I{SOURCE}", f"-I{TESTS}"]
OWNER = ["native_owner.c", "native_owner_lease.c", "native_launch_linux.c", "native_child_linux.c",
         "native_relay_linux.c"]
SERVICE = OWNER + ["native_service.c", "service_policy.c", "service_fixture_linux.c", "service_peer_linux.c",
                   "service_bootstrap_linux.c"]
SHARED = ["native_owner_lease.c", "native_launch_linux.c", "native_child_linux.c", "native_relay_linux.c",
          "native_service.c", "service_policy.c", "service_fixture_linux.c",
          "service_peer_linux.c", "service_bootstrap_linux.c"]


def path_of(name):
    return str(SOURCE / name) if (SOURCE / name).exists() else str(TESTS / name)


def compile_(work, sources, output, extra=()):
    result = subprocess.run([CC, *FLAGS, *extra, *map(path_of, sources), "-o", str(work / output)],
                            text=True, capture_output=True, timeout=180)
    return {"exit": result.returncode, "stderr": result.stderr[-3000:]}


def run(command, timeout=120):
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        return {"exit": result.returncode, "stdout": result.stdout[-3000:], "stderr": result.stderr[-3000:]}
    except subprocess.TimeoutExpired:
        return {"exit": "timeout"}


def main():
    if not sys.platform.startswith("linux"):
        raise SystemExit("the owner service builds and runs on Linux only")
    acceptance = ["-DNO_ACCEPTANCE_BUILD"]
    identity = [f"-DFIXTURE_UID={os.getuid()}u", f"-DFIXTURE_GID={os.getgid()}u"]
    results, expected = {}, {}
    with tempfile.TemporaryDirectory(prefix="owner-service-checks-") as directory:
        work = Path(directory)
        for name in SERVICE + ["service_main.c", "guardian_main.c", "guardian_journal.c", "guardian_epoch_linux.c",
                               "guardian_forward_linux.c", "guardian_seccomp_linux.c", "guardian_purge_linux.c",
                               "guardian_manifest_linux.c", "guardian_private_linux.c"]:
            results[f"object:{name}"] = compile_(work, [name], name + ".o", ["-c"])
            expected[f"object:{name}"] = 0
        results["entry"] = compile_(work, SERVICE + ["service_main.c", "service_fixture_manifest.c"], "service_main",
                                    identity)
        expected["entry"] = 0
        suites = {
            "service_acceptance": (["service_acceptance.c", *SHARED], [str(work / "service_main")], 0),
            "service_authority_acceptance": (["service_authority_acceptance.c", *SHARED], [], 0),
            "ownership_contract_acceptance": (["ownership_contract_acceptance.c", *SHARED[:4]], [], 0),
            "owner_core_acceptance": ([*OWNER, "owner_core_acceptance.c"], ["--suite=lifecycle"], 0),
            "service_e2e": (["service_e2e.c", *SHARED], None, None),
            "guardian_journal_acceptance": (["guardian_journal_acceptance.c", "guardian_journal.c"], [], 0),
            "purge_siphash_check": (["purge_siphash_check.c"], [], 0),
            "path_anchored_check": (["path_anchored_check.c"], [], 0),
            "purge_watch_acceptance": (["purge_watch_acceptance.c", "guardian_journal.c"], [], 0),
            "purge_roots_check": (["purge_roots_check.c", "guardian_manifest_linux.c", "service_policy.c"], [], 0),
            "guardian_acceptance": (["guardian_acceptance.c", "guardian_epoch_linux.c", "guardian_journal.c",
                                     "guardian_purge_linux.c"], [], 0),
            "guardian_forward_acceptance": (["guardian_forward_acceptance.c", "guardian_forward_linux.c",
                                             "service_peer_linux.c"], [], 0),
        }
        for name, (sources, arguments, code) in suites.items():
            results[f"compile:{name}"] = compile_(work, sources, name, acceptance)
            expected[f"compile:{name}"] = 0
            if arguments is not None and results[f"compile:{name}"]["exit"] == 0:
                results[f"run:{name}"] = run([str(work / name), *arguments])
                expected[f"run:{name}"] = code
        if results["compile:owner_core_acceptance"]["exit"] == 0:
            results["run:owner_core_contained"] = run([str(work / "owner_core_acceptance"), "--suite=contained"])
            expected["run:owner_core_contained"] = 77  # Unavailable without a protected fixture: by design.
            if results["compile:service_e2e"]["exit"] == 0:
                results["run:e2e"] = run([sys.executable, "-I", str(TESTS / "e2e_client.py"), str(work / "service_e2e"),
                                          str(work / "owner_core_acceptance"), str(REPOSITORY)])
                expected["run:e2e"] = 0
    failures = sorted(key for key, code in expected.items() if results.get(key, {}).get("exit") != code)
    print(json.dumps({"passed": not failures, "failures": failures, "results": results}))
    raise SystemExit(0 if not failures else 1)


if __name__ == "__main__":
    main()
