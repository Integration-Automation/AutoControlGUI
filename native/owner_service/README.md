# Linux owner service

An optional, root-installed service that runs AutoControl's Linux helper processes in
protected cgroup v2 trees. A helper and everything it starts live in one cgroup that
the helper's account cannot leave. Closing the helper's channel kills that whole tree,
including descendants that called `setsid()` or double-forked. A crash is cleaned up
when the guardian restarts.

The Python package never builds, installs or starts any of this. Without a binding
file, Linux helpers keep running as local processes. `agent_runtime_status()`
reports which mode a host is in under `helper_containment`.

## Status

The sources here pass their acceptance as root in one WSL distribution: Fedora 44,
kernel 6.18. The production gate in `native_owner.c` is still closed in the builds
`build.sh` produces, so protected launches are refused until a reviewed release opens
it. Only the acceptance build (`NO_PROTECTED_ACCEPTANCE`) opens the gate. Progress.md
lists what remains.

## Parts

| Path | What it is |
| --- | --- |
| `src/guardian_*.c`, `guardian.h` | Root guardian. It holds a durable epoch journal, creates and delegates one cgroup epoch, accepts clients, checks their account and namespaces, starts the service and recovers after crashes. |
| `src/service_*.c`, `native_service.*` | The service. It runs as its own account with CAP_SETUID, CAP_SETGID and CAP_SETPCAP only. It authenticates every packet by the sender's pidfd, issues leases, starts helpers and relays their I/O. |
| `src/native_owner*.c`, `native_launch_linux.c`, `native_relay_linux.c` | The owner core. Each helper gets its own record, worker thread, cgroup and descriptors. |
| `config/owner_manifest.example.c` | The compiled-in manifest: accounts, client namespaces, helper programs, paths. |
| `build.sh` | Builds `owner_service` and `owner_guardian` against a manifest. |
| `tests/run_checks.py` | Unprivileged acceptance: compiles everything and runs the suites. |
| `tests/protected_run.py` | Root acceptance on a disposable host. It provisions accounts and a cgroup subtree, runs real sessions, crashes and recovery, then removes everything. |

## Requirements

- Linux with cgroup v2 and pidfs: kernel 6.13 or later, with `PIDFD_GET_INFO`,
  `SO_PASSPIDFD` and `cgroup.kill`.
- glibc headers that define `PIDFD_GET_INFO` (glibc 2.42 or later).
- A C11 compiler.

## Install (administrator)

1. Create a service account and a payload account, both distinct from the client
   accounts.
2. Copy `config/owner_manifest.example.c` to `owner_manifest.c`, fill in every
   value marked `EDIT`, and review it.
3. Run `build.sh owner_manifest.c build/`. Install `owner_guardian` and
   `owner_service` as root-owned files that nobody else can write, at the paths the
   manifest names.
4. Create the cgroup subtree beneath the cgroup2 mount, root-owned and mode 0755, and
   the root-only state directory.
5. Run `owner_guardian` as root under the host's supervisor. It creates the listener
   and starts the service itself.
6. Write `/etc/je_auto_control/owner_service.json`. It must be root-owned and not
   writable by anyone else, and holds the listener path and the exact helper argv
   for each policy:

   ```json
   {"endpoint": "/run/je_auto_control/owner.sock",
    "policies": [{"argv": ["/usr/bin/python3", "-I", "-u", "-m",
                           "je_auto_control.utils.agent_runtime.native_worker"], "policy": 1}]}
   ```

## Verify

```sh
python3 tests/run_checks.py              # unprivileged suites, any Linux build host
sudo python3 -I tests/protected_run.py "$PWD" <repository root>   # disposable host only
```

`protected_run.py` creates system accounts, `/sys/fs/cgroup/autocontrol-test`,
`/var/lib/autocontrol-test`, `/run/autocontrol-test` and `/opt/autocontrol-test`. It
removes them again afterwards. Run it only on a machine or VM meant for testing.
