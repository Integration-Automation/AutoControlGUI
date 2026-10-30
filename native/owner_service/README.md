# Linux owner service

An optional, root-installed service that runs AutoControl's Linux helper processes in
protected cgroup v2 trees. A helper and everything it starts live in one cgroup that
the helper's account cannot leave. Closing the helper's channel kills that whole tree,
including descendants that called `setsid()` or double-forked. A crash is cleaned up
when the guardian restarts.

The Python package never builds, installs or starts any of this. Without a binding
file, Linux helpers keep running as local processes. With one, helpers that drive the
user's desktop or browser still run locally: a protected helper runs as its own ID with
an empty environment and cannot reach the X or Wayland session. The service carries
display-free helpers, such as dependency probes and remote device helpers. `agent_runtime_status()`
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
  epoch, and reclaims the retiring one when its last lease ends. Up to three epochs
  retire at a time; beyond that, new opens get CAPACITY until one is reclaimed. A connection without an
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
  its epoch's slice, plus its lease position; 128 IDs per range, with no account
  needed. No two live helpers share
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
- Payload ranges hold four slices of 32 IDs. The guardian picks each epoch's slice
  itself, never one another running epoch uses, and sends it in the grant, so up to three
  spent epochs can retire beside the current one; a further retirement waits for a slot.
  Each slice is purged in a child process after its epoch ends and is not handed out
  again until that purge finishes; meanwhile, if no other slice is free, there is no
  current epoch: helpers' own connections still reach their retiring epoch, up to 32
  other clients are held until one starts, and further ones are dropped.
  A payload-owned directory the purge cannot remove where it is (another ID wrote into
  it, or it lies deeper than the 64-level walk) is moved, inode-checked, into a root-only
  quarantine on the same filesystem and taken apart there 64 levels at a time: its name
  is free at once and every payload-owned file below it, tmpfs pages included, is
  released. The quarantine is made when first needed under a random name and recognised
  by its inode, so a name someone else took first hides nothing; it is locked while its
  purge runs, so purges of two slices leave each other's alone. An emptied one is
  removed, and only what other IDs own (out of every payload's reach) stays in one.
  Another ID's directory at the depth bound stays put and is walked from its own top,
  up to 4096 of them (or what the descriptor limit leaves room for), with a log line
  beyond. A walk never enters another mount nor judges an object on one. Each walk
  enters a directory once, by its exact inode number and a digest of its file handle
  (inode generation included) keyed afresh for every purge, so neither a reused inode
  number nor a computed digest is taken for an earlier directory: one met again is
  skipped, and a payload directory met again outside the quarantine makes the purge run
  again. The size of what others
  keep under a root only makes a purge slower. A listing growing far past its size while
  it is read, which only a live user causes, stops it, and it runs again, as does one
  that could not move a payload directory into the quarantine, before its slice is
  handed out; a live local user can therefore delay a slice. Directories on another
  device of the same mount (btrfs subvolumes) are entered only when a payload owns them,
  and payloads cannot create subvolumes or snapshots or make one read-only. Each purge
  runs in a child with a mount namespace of its own, a slave of the host's so nothing it
  does propagates out; every root and SysV IPC table is opened before anything is
  detached. A walk that meets an entry on another mount (a payload directory another user
  covered with a FUSE mount, say) detaches that mount in its own namespace, by the
  descriptor of the mount's root opened relative to the walked directory, never by a
  path, and removes what lies beneath; removing a payload mountpoint detaches the host's
  mount too, and whatever that mount held is gone with it. A mount it cannot detach makes
  the purge run again.
  On the host's own roots, which helpers reach only where the epoch's private mounts do
  not stand (a world-writable directory not listed as a purge root), payload files can
  escape a purge only with another local user's help: inside another ID's directories past
  the deferral limit, inside another ID's btrfs subvolume, or renamed behind the walk by
  that user while it runs. Entries are opened only
  without crossing a mount (RESOLVE_NO_XDEV) and judged by those descriptors; removal and
  moves by name stop at a mount point (EBUSY) without reaching what it shows. So another
  user's FUSE mount (an sshfs or AppImage mount, live, dead, or with a root inode the
  kernel marked bad) is never asked anything and is detached like any other, also when it
  is placed on an entry while the walk runs. POSIX message queues are purged through a
  fresh mqueue mount made with the mount API and attached nowhere, so they are reached
  whether or not the host mounted /dev/mqueue. A purge child whose progress stands still
  for a minute is killed and run again, the allowance doubling after each stall of its
  slice in a row (up to 64 minutes) so a slow but finite call gets through. A child stuck
  where no signal reaches it keeps its slice until it ends; the guardian goes on
  meanwhile, at startup too. No payload file can carry a
  set-user- or set-group-ID bit, so what escapes is data, not an identity, but a later
  helper with the same ID may find it.
  Only an object that can be neither removed, moved nor closed off taints its slice,
  and startup purges each slice once, after the previous run's epochs are dead, so one
  stubborn leftover never stops the guardian. A helper's own connection (a nested parent
  opening children) goes to the epoch that runs its slice, retiring or not; a policy that
  may start nested children needs `record_capacity` above `client_lease_quota`, which the
  manifest check does not enforce (a lower capacity only answers CAPACITY sooner).
  `epoch-N` itself is bounded (depth 40, 4096 descendants, the records' limits plus room
  for the service) and delegated only after `records` and the service leaf exist. A next
  epoch that cannot be planned or started is retried after 1, 2, 4 ... up to 30 seconds
  from the main loop, which keeps answering a stop request, retiring epochs and purges;
  so does a service that ends within a second of starting. A stop kills every epoch and
  abandons running purges; the next start purges.
  A manifest purge root must sit under real directories that exist when the guardian
  starts, are root's and are writable by no one else (sticky ones included: others may
  create a missing name there); the guardian refuses the manifest otherwise, naming the
  root, and checks again what each root resolves to at every purge. Write a root without
  a trailing slash: with one, the root itself counts as an ancestor and must be so too. A world-writable
  mount below a sticky directory (a 1777 mount at `/tmp/foo`, say) is therefore
  unsupported: the `/tmp` walk does not enter it and it cannot be listed.
  Every directory payload IDs can write must be a purge root: the defaults are `/tmp`,
  `/var/tmp`, `/dev/shm`, `/run/lock` and `/var/crash`, and the manifest lists any other
  (`purge_roots`, any other world-writable directory) and caps every running epoch together (`subtree_pids_max`,
  `subtree_memory_max`); up to four epochs run at once, so either set those or cap the
  subtree's parent. Before building the filter, the guardian refuses a manifest the service would
  refuse, or whose payload IDs are below 1000 or known to the host's user and group
  databases. Payloads cannot use kernel keyrings, nor set a set-user- or set-group-ID
  bit on any file (chmod family, a creating open, mknod; openat2 and io_uring, including
  entering or registering a ring another process passed in, answer ENOSYS), so copying a
  set-group-ID directory's mode fails in a payload. With CAP_SETUID and CAP_SETGID the
  service can still forge the UID or GID in SCM_CREDENTIALS; this project authenticates by
  pidfd, but anything trusting SCM_CREDENTIALS alone (journald's `_UID`, for example)
  should not take a service-sent value at face value.
- Helpers start with umask 077, and the guardian caps the epoch's `records` cgroup at
  the per-helper process and memory limits times the record capacity, so tmpfs pages a
  killed helper left behind still count against the epoch.
- Each epoch's service and every helper it starts run in a mount namespace and an IPC
  namespace of their own, which the guardian makes when it starts the service: a fresh
  tmpfs, with the mode and owner of the host's directory, stands over `/tmp`, `/var/tmp`,
  `/dev/shm`, `/run/lock`, `/var/crash` and every manifest purge root, and SysV IPC objects
  and POSIX message queues belong to the epoch alone. What a helper leaves there is out of
  every other user's sight and reach, and is gone once the epoch's last process is, unless
  a helper itself handed a descriptor into it to a process outside the epoch. Lock files in
  the epoch's `/run/lock` exclude only processes of the same epoch. A root that does not
  exist when an epoch starts is covered from the next epoch on; until then the purge walks
  it on the host as before. Each tmpfs is `noexec`, `nosymfollow` or read-only where the
  host's mount is (a read-only host root gives the epoch a read-only, empty one), and its
  pages count against the epoch's memory limit. A manifest is refused, since the epoch
  would not see the path, when its listener, service executable or a policy executable
  lies under any of these roots, or a policy working directory, or a path a policy's fixed
  arguments or environment values name, lies below one. An argument is judged whole and
  after its first `=`, an environment value after its `=`, each part of a `:` list alone; a
  relative part with a `/` is judged from the policy's working directory, and an empty or
  `.` part of an environment value is that directory, refused when it is a root (a search
  list there would read the epoch's shared tmpfs). Not judged: bare words, a second `=`,
  `,` lists, option values attached as in `-I/tmp/x`, and an interpreter a script names on
  its `#!` line. Each path
  is compared as written (its spelling tidied: repeated slashes and `.` dropped) and
  resolved component by component: every directory on the way, every link and every name a
  link leads through is checked, and what is not made yet is judged by where it would be.
  What cannot be resolved (a link loop, an unreadable directory, a `..` below a name not
  made yet, a root written with `..`) is refused too. Each epoch start checks the
  listener and the service executable again, and does not start if a root made since hides
  one. The guardian accepts a payload ID's connection only from the mount namespace of the
  epoch that runs its slice.
- When an epoch is reclaimed, the guardian also removes the files under `/tmp`, `/var/tmp`,
  `/dev/shm`, `/run/lock` and `/var/crash` (and any manifest `purge_roots`), the POSIX message queues
  and the SysV IPC objects that payload IDs own (as systemd's DynamicUser with RemoveIPC
  does), so a later helper with the same ID finds none of an earlier one's, beyond the
  escapes listed above. Helpers start with a core limit of 0, hard limit included: no core
  file is written, systemd-coredump stores none, and apport's crash reports land in
  `/var/crash`, a default purge root. A crash report its handler finishes only after the
  reclaim purge (a crash at the moment the epoch is killed) stays until that slice's next
  purge. A pipe or socket `core_pattern` to any other handler may keep a crashed helper's
  memory (see Requirements).

## Parts

| Path | What it is |
| --- | --- |
| `src/guardian_*.c`, `guardian.h` | Root guardian. It holds a durable epoch journal, creates and delegates one cgroup epoch, accepts clients, checks their account and namespaces, starts the service and recovers after crashes. |
| `src/service_*.c`, `native_service.*` | The service. It runs as its own account with CAP_SETUID, CAP_SETGID and CAP_SETPCAP only. It authenticates every packet by the sender's pidfd, issues leases, starts helpers and relays their I/O. |
| `src/native_owner*.c`, `native_launch_linux.c`, `native_relay_linux.c` | The owner core. Each helper gets its own record, worker thread, cgroup and descriptors. |
| `config/owner_manifest.example.c` | The compiled-in manifest: accounts, client namespaces, helper programs, paths. |
| `build.sh` | Builds `owner_service` and `owner_guardian` against a manifest. |
| `tests/run_checks.py` | Unprivileged acceptance: compiles everything and runs the suites. |
| `tests/purge_watch_acceptance.c`, `tests/purge_roots_check.c`, `tests/purge_fault_acceptance.c` | The purge stall watch, the manifest purge-root check and the purge's fault paths (the last, and the root cases of the second, run as root under `protected_run.py`). |
| `tests/protected_run.py` | Root acceptance on a disposable host. It provisions accounts and a cgroup subtree, runs real sessions, crashes and recovery, then removes everything. |

## Requirements

- Linux with cgroup v2 and pidfs: kernel 6.13 or later, with `PIDFD_GET_INFO`,
  `SO_PASSPIDFD` and `cgroup.kill`.
- glibc headers that define `PIDFD_GET_INFO` (glibc 2.42 or later).
- A C11 compiler.
- POSIX message queues are reached through the mount API (`fsopen`), which the
  guardian's own confinement must allow; if it does not, `/dev/mqueue` must be the mqueue
  filesystem, or purges never complete.
- journald without per-UID journal files (`SplitMode=none`, or volatile storage): with
  the default `SplitMode=uid` and persistent storage, what one helper logs (and possibly
  a crashed helper's coredump metadata, its environment included) is kept in a
  `user-<uid>.journal` the next helper with the same ID may read.
- `kernel.core_pattern` a file pattern, or a pipe to systemd-coredump or apport; a pipe
  to any other handler (ABRT, say) or a socket (`@`) may keep crashed helpers' memory, and
  the guardian logs a warning for one, or for a pattern it cannot read, at startup.
- Where the mount API is refused, `/dev/mqueue` must show the guardian's own IPC
  namespace: the purge checks only that it is the mqueue filesystem.
- Every directory a helper can reach and write is a purge root: `/tmp`, `/var/tmp`,
  `/dev/shm`, `/run/lock` and `/var/crash` are, any other goes into the manifest's
  `purge_roots`. A filesystem that does not keep its writers' IDs cannot be one; keep
  helpers out of it instead. Under WSL the drive automounts (`/mnt/c` and the others) are
  writable by every account, and what a helper writes there shows up owned by the
  distribution's default user: mount them with `umask=022` or tighter (the `[automount]`
  `options` in `/etc/wsl.conf`) or turn automount off. `/mnt/wsl` and `/mnt/wslg` are
  writable by everyone too. WSL also pipes `kernel.core_pattern` to
  `/wsl-capture-crash`, a handler the guardian does not know.

## Install (administrator)

1. Create a service account with its own primary group, and a socket group. Add the
   client account to the socket group as a supplementary member. Reserve 128 user IDs and
   the same 128 group IDs, at 1000 or above, that nothing else uses for helpers; they need
   no accounts.
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

`installed_host_acceptance.py` (root, disposable host) follows the install steps above
with the example manifest's values filled in, compares the installed files against the
build, starts the guardian, checks the listener, the epoch's private roots and that the
closed gate refuses a lease, reports which host requirements the host meets, and removes
everything again:

```sh
sudo python3 -I tests/installed_host_acceptance.py "$PWD" <repository root> <client account>
```

`protected_run.py` creates system accounts, `/sys/fs/cgroup/autocontrol-test`,
`/var/lib/autocontrol-test`, `/run/autocontrol-test` and `/opt/autocontrol-test`. It
removes them again afterwards. Run it only on a machine or VM meant for testing.
