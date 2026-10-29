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
kernel 6.18. An independent review found the blockers fixed below; its remaining
findings are listed in Progress.md. The production gate in `native_owner.c` is still
closed in the builds `build.sh` produces, so protected launches are refused until a
reviewed release opens it. Only the acceptance build (`NO_PROTECTED_ACCEPTANCE`) opens
the gate.

- Clients renew their leases in the background (`OP_RENEW`), up to the manifest's
  `lease_max_age_ns`, so an idle helper is not killed when one lifetime ends.
- When the client's quota or the record slots of an epoch are spent and no lease or
  connection is open, the service drains, and the same guardian reclaims the epoch
  and grants the next one. A spent epoch that still holds open leases retires beside the
  next instead: it keeps serving those leases, the guardian hands new clients to the next
  epoch, and reclaims the retiring one when its last lease ends. At most one epoch retires
  at a time; if the next is spent too while it still runs, new opens get CAPACITY. A connection without an
  open lease holds a spent epoch for at most 5 seconds, so an idle or abandoned client
  cannot keep the host from rolling over; the Python channel connects only at its first
  request, and reports a connection turned away before it has a lease as
  `AgentControlBusy`.
- The service runs with a bounding set of only CAP_SETUID, CAP_SETGID and
  CAP_SETPCAP, `SECBIT_NOROOT` locked, and no_new_privs. Those guard only exec, so a
  seccomp filter, inherited by every payload, also confines the calls themselves:
  `setresuid`/`setresgid` may name only the service's and the manifest's payload IDs,
  `setgroups` only an empty list, the other set*id calls fail, and no user namespace
  can be created (`clone3` answers ENOSYS, so payloads start with `clone` and are moved
  into their cgroup before they run). A code-execution bug in the service therefore
  reaches the payload ranges, not root, the client or another group. The filter is
  built for x86-64 and arm64 only.
- Payloads hold no supplementary group. A nested-capable payload reaches the guardian
  through an ACL on the listener that names every client account in the guardian's
  manifest, so `/run` must support POSIX ACLs (tmpfs does).
- Every helper runs as its own user and group ID: the policy's payload range base, plus
  its epoch's half (by counter parity), plus its lease position; 64 IDs per range, with
  no account needed. No two live helpers share
  an account, so none can ptrace, signal or take descriptors from another. Payload ranges
  must not contain the guardian's, the service's, the client's or the socket group's IDs;
  two policies' ranges are equal or disjoint; a nested child draws from its parent's
  range. A service serves exactly one client account.
- A helper whose policy may start nested children may open at most the manifest's
  `nested_lease_quota` child leases per epoch; children no longer count against an
  account's share. The guardian hands over at most 32 connections per account per
  second, and the service takes every pending handoff each turn, so one account's
  connection flood cannot crowd out another's.
- The guardian walks the cgroup subtree from the mount one component at a time and
  refuses any cgroup on the way (mount and subtree included) whose directory or
  `cgroup.procs`, `cgroup.threads` or `cgroup.subtree_control` belongs to another account
  or is writable by others: a delegated cgroup there could move helpers out of the epoch.
- Helpers start with umask 077, and the guardian caps the epoch's `records` cgroup at
  the per-helper process and memory limits times the record capacity, so tmpfs pages a
  killed helper left behind still count against the epoch.
- When an epoch is reclaimed, the guardian removes the files under `/tmp`, `/var/tmp`,
  `/dev/shm` and `/dev/mqueue` and the SysV IPC objects that payload IDs own (as
  systemd's DynamicUser with RemoveIPC does), so a later helper with the same ID finds
  nothing of an earlier one.

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

1. Create a service account with its own primary group, and a socket group. Add the
   client account to the socket group as a supplementary member. Reserve 64 user IDs and
   the same 64 group IDs that nothing else uses for helpers; they need no accounts.
2. Copy `config/owner_manifest.example.c` to `owner_manifest.c`, fill in every
   value marked `EDIT`, and review it.
3. Run `build.sh owner_manifest.c build/`. Install `owner_guardian` and
   `owner_service` as root-owned files that nobody else can write, at the paths the
   manifest names.
4. Create the cgroup subtree beneath the cgroup2 mount, root-owned and mode 0755, and
   the root-only state directory. Every directory above either must be root's (or the
   manifest's administrator's) and not writable by others unless sticky. Enable the `pids` and `memory` controllers in every
   ancestor's `cgroup.subtree_control` down to the subtree's parent (systemd hosts
   usually have them at the root already); the guardian enables them below that and
   refuses to start without them (`prepare operation 4 errno 2`).
5. Run `owner_guardian` as root under the host's supervisor (for example
   `Restart=on-failure`). It creates the listener, starts the service and rolls over to
   a fresh epoch itself; it exits 0 only when asked to stop. The listener's directory
   (for example `/run/je_auto_control`, root-owned, mode 0755) and the cgroup subtree
   with its enabled controllers live on filesystems that start empty at every boot:
   recreate them before the guardian starts, for example with `tmpfiles.d` and an
   `ExecStartPre=` step, or the guardian refuses to start.
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
