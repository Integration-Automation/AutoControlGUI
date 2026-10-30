"""Protected acceptance, run as root on a disposable Linux host or VM only.

Usage: python3 -I protected_run.py <native/owner_service directory> <repository root>
Provisions three system accounts and a socket group, a root-owned cgroup2 subtree, a state directory, a
runtime directory and the binaries; runs the guardian, the gate-open service and a real
client; and removes everything it created again, whatever happens. Prints one JSON object.
"""
import grp
import json
import os
import pwd
import shutil
import signal
import subprocess
import sys
import ctypes
import errno
import struct
import tempfile
import threading
import time

SOURCE, REPOSITORY = sys.argv[1], sys.argv[2]
SRC, TESTS = os.path.join(SOURCE, "src"), os.path.join(SOURCE, "tests")
CC = os.environ.get("CC", "cc")
OPT, STATE, RUN = "/opt/autocontrol-test", "/var/lib/autocontrol-test", "/run/autocontrol-test"
SUBTREE = "/sys/fs/cgroup/autocontrol-test"
OUTER, STATE2 = "/sys/fs/cgroup/autocontrol-outer", "/var/lib/autocontrol-test2"
ENDPOINT = RUN + "/owner.sock"
CLIENT = "user"
ACCOUNTS = ("acsvc", "acother")
# Helpers run as IDs from this range: an epoch's slice, then its lease position. No account
# is created.
PAYLOAD_BASE, PAYLOAD_IDS, EPOCH_IDS = 62000, 128, 32
SOCKET_GROUP = "acsock"
ROLLOVER_SESSIONS = 10  # More than the manifest's quota of 8 leases per epoch.
SERVICE_SOURCES = ["native_owner.c", "native_owner_lease.c", "native_launch_linux.c", "native_child_linux.c",
                   "native_relay_linux.c", "service_peer_linux.c"]
created_accounts = []
created_groups = []
enabled_controllers = []
ROOT_CONTROL = "/sys/fs/cgroup/cgroup.subtree_control"
report = {"evidence": "protected acceptance in one WSL distro", "steps": {}}


def run(args, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, timeout=kwargs.pop("timeout", 120), **kwargs)


def locate(name):
    return os.path.join(SRC, name) if os.path.exists(os.path.join(SRC, name)) else os.path.join(TESTS, name)


def gcc(sources, output, defines=(), acceptance=False):
    base = [CC, "-std=c11", "-pthread", "-Wall", "-Wextra", "-Werror", "-I" + SRC, "-I" + TESTS]
    if acceptance:
        base.append("-DNO_ACCEPTANCE_BUILD")
    result = run(base + list(defines) + [locate(s) for s in sources] + ["-o", output])
    if result.returncode:
        raise RuntimeError(f"compile {output}: {result.stderr[-3000:]}")
    os.chmod(output, 0o755)


def provision():
    try:
        grp.getgrnam(SOCKET_GROUP)
    except KeyError:
        result = run(["groupadd", "--system", SOCKET_GROUP])
        if result.returncode:
            raise RuntimeError(f"groupadd: {result.stderr}")
        created_groups.append(SOCKET_GROUP)
    taken = [i for i in range(PAYLOAD_BASE, PAYLOAD_BASE + PAYLOAD_IDS) if _uid_taken(i) or _gid_taken(i)]
    if taken:
        raise RuntimeError(f"payload range already in use: {taken[:4]}")
    for name in ACCOUNTS:
        try:
            pwd.getpwnam(name)
        except KeyError:
            # Every account has its own primary group. acother joins the socket group, so it
            # reaches the socket and only the guardian's principal check can refuse it.
            extra = ["--groups", SOCKET_GROUP] if name == "acother" else []
            result = run(["useradd", "--system", "--no-create-home", "--shell", "/usr/sbin/nologin",
                          "--user-group", *extra, name])
            if result.returncode:
                raise RuntimeError(f"useradd {name}: {result.stderr}")
            created_accounts.append(name)
    # The administrator's step: pids and memory enabled down to the subtree's parent.
    with open(ROOT_CONTROL) as handle:
        present = handle.read().split()
    for controller in ("pids", "memory"):
        if controller not in present:
            with open(ROOT_CONTROL, "w") as handle:
                handle.write("+" + controller)
            enabled_controllers.append(controller)
    result = run(["usermod", "--append", "--groups", SOCKET_GROUP, CLIENT])
    if result.returncode:
        raise RuntimeError(f"usermod {CLIENT}: {result.stderr}")
    for path, mode in ((OPT, 0o755), (STATE, 0o700), (RUN, 0o755), (SUBTREE, 0o755)):
        os.makedirs(path, exist_ok=False)
        if not path.startswith("/sys/"):
            os.chmod(path, mode)


def namespaces():
    values = {}
    for key, name in (("NS_USER", "user"), ("NS_PID", "pid"), ("NS_MOUNT", "mnt"), ("NS_CGROUP", "cgroup")):
        status = os.stat(f"/proc/self/ns/{name}")
        values[key], values["NS_DEVICE"] = status.st_ino, status.st_dev
    return values


def build():
    service = pwd.getpwnam("acsvc")
    client = pwd.getpwnam(CLIENT)
    values = {"SERVICE_UID": service.pw_uid, "SERVICE_GID": service.pw_gid, "PAYLOAD_UID": PAYLOAD_BASE,
              "PAYLOAD_GID": PAYLOAD_BASE, "CLIENT_UID": client.pw_uid, "CLIENT_GID": client.pw_gid,
              "SOCKET_GID": grp.getgrnam(SOCKET_GROUP).gr_gid,
              **namespaces()}
    defines = [f"-D{key}={value}u" if not key.startswith("NS_") else f"-D{key}={value}ULL"
               for key, value in values.items()]
    defines.append(f'-DPAYLOAD_EXECUTABLE="{OPT}/owner_core_acceptance"')
    defines += [f'-DNESTED_PARENT="{OPT}/nested_parent.py"', f'-DREPOSITORY="{REPOSITORY}"',
                f'-DREMOTE_HELPER="{OPT}/remote_helper.py"',
                f'-DENDPOINT="{ENDPOINT}"']
    for script in ("nested_parent.py", "remote_helper.py"):
        shutil.copy(os.path.join(TESTS, script), f"{OPT}/{script}")
        os.chmod(f"{OPT}/{script}", 0o644)
    gcc(SERVICE_SOURCES + ["native_service.c", "service_policy.c", "service_bootstrap_linux.c", "service_main.c",
                           "protected_manifests.c"],
        OPT + "/service_main", defines + ["-DNO_PROTECTED_ACCEPTANCE"])
    gcc(SERVICE_SOURCES + ["guardian_main.c", "guardian_epoch_linux.c", "guardian_journal.c",
                           "guardian_forward_linux.c", "guardian_seccomp_linux.c", "guardian_purge_linux.c",
                           "guardian_manifest_linux.c", "guardian_private_linux.c", "service_policy.c",
                           "protected_manifests.c"], OPT + "/guardian", defines)
    gcc(["native_owner.c", "native_owner_lease.c", "native_launch_linux.c", "native_child_linux.c",
         "native_relay_linux.c", "owner_core_acceptance.c"], OPT + "/owner_core_acceptance", acceptance=True)
    gcc(["seccomp_probe.c", "guardian_seccomp_linux.c", "protected_manifests.c"], OPT + "/seccomp_probe", defines)
    gcc(["purge_fault_acceptance.c"], OPT + "/purge_fault")
    gcc(["purge_roots_check.c", "guardian_manifest_linux.c", "service_policy.c"], OPT + "/purge_roots_check")
    gcc(SERVICE_SOURCES + ["guardian_main.c", "guardian_epoch_linux.c", "guardian_journal.c",
                           "guardian_forward_linux.c", "guardian_seccomp_linux.c", "guardian_purge_linux.c",
                           "guardian_manifest_linux.c", "guardian_private_linux.c", "service_policy.c",
                           "protected_manifests.c"],
        OPT + "/guardian_one_retiring", defines + ["-DGUARDIAN_RETIRING_LIMIT=1"])
    taken = pwd.getpwnam("acother").pw_uid
    gcc(SERVICE_SOURCES + ["guardian_main.c", "guardian_epoch_linux.c", "guardian_journal.c",
                           "guardian_forward_linux.c", "guardian_seccomp_linux.c", "guardian_purge_linux.c",
                           "guardian_manifest_linux.c", "guardian_private_linux.c", "service_policy.c",
                           "protected_manifests.c"],
        OPT + "/guardian_taken_range",
        [d for d in defines if not d.startswith(("-DPAYLOAD_UID=", "-DPAYLOAD_GID="))]
        + [f"-DPAYLOAD_UID={taken}u", f"-DPAYLOAD_GID={PAYLOAD_BASE}u"])
    gcc(SERVICE_SOURCES + ["guardian_main.c", "guardian_epoch_linux.c", "guardian_journal.c",
                           "guardian_forward_linux.c", "guardian_seccomp_linux.c", "guardian_purge_linux.c",
                           "guardian_manifest_linux.c", "guardian_private_linux.c", "service_policy.c",
                           "protected_manifests.c"],
        OPT + "/guardian_outer", defines + ['-DPROTECTED_SUBTREE="autocontrol-outer/inner"',
                                            f'-DPROTECTED_STATE="{STATE2}"'])
    report["accounts"] = {k: v for k, v in values.items() if not k.startswith("NS_")}


def _dead_fuse_mount(path, owner):
    """A FUSE mount at `path` belonging to `owner`, without allow_other, whose daemon is gone:
    root is refused a getattr on it, as on any user's sshfs or AppImage mount."""
    libc = ctypes.CDLL(None, use_errno=True)
    device = os.open("/dev/fuse", os.O_RDWR)
    options = f"fd={device},rootmode=40000,user_id={owner},group_id={owner}".encode()
    mounted = libc.mount(b"cover", path.encode(), b"fuse", 0, options) == 0
    os.close(device)  # The daemon is gone; the mount stays, dead.
    return mounted


def _bad_fuse_mount(path, owner):
    """A FUSE mount at `path` belonging to `owner`, without allow_other, whose root inode the
    kernel marked bad: its daemon answered the owner's stat with a size past LLONG_MAX, then
    went away. A getattr on it fails with EIO for everyone, even with an empty mask."""
    libc = ctypes.CDLL(None, use_errno=True)
    device = os.open("/dev/fuse", os.O_RDWR)
    options = f"fd={device},rootmode=40000,user_id={owner},group_id={owner}".encode()
    if libc.mount(b"cover", path.encode(), b"fuse", 0, options) != 0:
        os.close(device)
        return False

    def serve():
        for _ in range(8):
            try:
                request = os.read(device, 1 << 20)
            except OSError:
                return
            length, opcode, unique = struct.unpack_from("<IIQ", request)
            if opcode == 26:  # INIT: protocol 7.31, nothing optional.
                body = struct.pack("<IIIIHHIIHHI", 7, 31, 65536, 0, 16, 12, 4096, 1, 32, 0, 0) + bytes(28)  # 64
            elif opcode == 3:  # GETATTR: a directory whose size no kernel accepts.
                attr = struct.pack("<QQQQQQIIIIIIIIII", 1, 1 << 63, 0, 0, 0, 0, 0, 0, 0, 0o40755, 2,
                                   owner, owner, 0, 4096, 0)
                body = struct.pack("<QII", 0, 0, 0) + attr
            else:
                os.write(device, struct.pack("<IiQ", 16, -38, unique))
                continue
            os.write(device, struct.pack("<IiQ", 16 + len(body), 0, unique) + body)
            if opcode == 3:
                return

    server = threading.Thread(target=serve, daemon=True)
    server.start()
    stat = subprocess.run(["runuser", "-u", pwd.getpwuid(owner).pw_name, "--", "stat", path],
                          capture_output=True, text=True, timeout=20,
                          env={"LC_ALL": "C", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"})
    server.join(timeout=10)
    os.close(device)  # The daemon is gone; the mount stays, its root inode bad.
    return "Input/output error" in stat.stderr


QUEUE_NAME = b"/autocontrol-left-queue"


def _payload_queue(uid, name=QUEUE_NAME):
    """A POSIX message queue `uid` made and left, holding one message."""
    libc = ctypes.CDLL(None, use_errno=True)  # Before the fork: no loader lock taken in the child.
    child = os.fork()
    if child == 0:
        try:
            os.setgid(uid)
            os.setuid(uid)
            queue = libc.mq_open(name, os.O_CREAT | os.O_RDWR, 0o600, None)
            os._exit(0 if queue >= 0 and libc.mq_send(queue, b"left", 4, 0) == 0 else 1)
        except BaseException:  # reason: a forked child must never return into the harness
            os._exit(2)
    return os.waitpid(child, 0)[1] == 0


def _queue_exists(name=QUEUE_NAME):
    """True when the queue is there (it is then removed); None when that cannot be told."""
    libc = ctypes.CDLL(None, use_errno=True)
    queue = libc.mq_open(name, os.O_RDONLY)
    if queue >= 0:
        libc.mq_close(queue)
        libc.mq_unlink(name)
        return True
    return False if ctypes.get_errno() == errno.ENOENT else None


def _drain(stream, sink):
    for line in iter(stream.readline, ""):
        sink.append(line)


def _ignore_sigchld():
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)


def start_guardian(binary="guardian", ignore_sigchld=False):
    # ignore_sigchld: started as a careless parent might start it, with SIGCHLD ignored.
    guardian = subprocess.Popen([OPT + "/" + binary], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, text=True, env={},
                                preexec_fn=_ignore_sigchld if ignore_sigchld else None)
    # Read while it runs: a guardian that logs past the pipe's buffer must never block.
    guardian.log = []
    guardian.drainer = threading.Thread(target=_drain, args=(guardian.stderr, guardian.log), daemon=True)
    guardian.drainer.start()
    limit = time.monotonic() + 15
    while not os.path.exists(ENDPOINT) and time.monotonic() < limit:
        if guardian.poll() is not None:
            guardian.drainer.join(timeout=5)
            raise RuntimeError(f"guardian exited {guardian.returncode}: {''.join(guardian.log)}")
        time.sleep(0.05)
    if not os.path.exists(ENDPOINT):
        raise RuntimeError("guardian never published its listener")
    time.sleep(0.3)  # The grant exchange completes before clients are forwarded anyway.
    return guardian


def stop_guardian(guardian, sig=signal.SIGTERM):
    guardian.send_signal(sig)
    try:
        guardian.wait(timeout=30)
    except subprocess.TimeoutExpired:
        guardian.kill()
        guardian.wait()
    drainer = getattr(guardian, "drainer", None)
    if drainer is None:  # Started elsewhere, without a drainer.
        return guardian.returncode, guardian.stderr.read()[-60000:]
    drainer.join(timeout=10)
    text = "".join(guardian.log)
    # Startup lines (the core_pattern warning) come first: the head is kept with the tail.
    return guardian.returncode, text if len(text) <= 64000 else text[:4000] + text[-60000:]


def client(mode, account=CLIENT):
    return subprocess.Popen(["runuser", "-u", account, "--", "/usr/bin/python3", "-I",
                             os.path.join(TESTS, "protected_client.py"), REPOSITORY, ENDPOINT, mode],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def read_json(process):
    line = process.stdout.readline()
    return json.loads(line) if line else {"eof": True, "stderr": process.stderr.read()[-2000:]}


def epochs():
    return sorted(name for name in os.listdir(SUBTREE) if name.startswith("epoch-"))


def procs_under(path):
    found = []
    for directory, _subdirs, files in os.walk(path):
        if "cgroup.procs" in files:
            with open(os.path.join(directory, "cgroup.procs")) as handle:
                found += [(directory, int(pid)) for pid in handle.read().split()]
    return found


def status_of(pid):
    fields = {}
    with open(f"/proc/{pid}/status") as handle:
        for line in handle:
            key, _, value = line.partition(":")
            fields[key] = value.strip()
    return {"uid": fields["Uid"].split()[0], "cap_eff": fields["CapEff"], "cap_bnd": fields["CapBnd"],
            "no_new_privs": fields.get("NoNewPrivs"), "seccomp": fields.get("Seccomp"),
            "threads": fields.get("Threads"),
            "gid": fields["Gid"].split()[0], "groups": fields.get("Groups", "").split()}


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _uid_taken(value):
    try:
        pwd.getpwuid(value)
        return True
    except KeyError:
        return False


def _gid_taken(value):
    try:
        grp.getgrgid(value)
        return True
    except KeyError:
        return False


def payload_owned_anywhere():
    """Every path under the purge roots that a payload ID still owns, quarantines included."""
    found = []
    for top in ("/tmp", "/var/tmp", "/dev/shm", "/run/lock", "/var/crash"):
        for directory, subdirs, files in os.walk(top, followlinks=False):
            for name in subdirs + files:
                path = os.path.join(directory, name)
                try:
                    if 0 <= os.lstat(path).st_uid - PAYLOAD_BASE < PAYLOAD_IDS:
                        found.append(path)
                except OSError:
                    pass
    return found[:10]


def _closed_off(path):
    try:
        status = os.lstat(path)
    except OSError:
        return False
    return status.st_uid == 0 and status.st_gid == 0 and (status.st_mode & 0o7777) == 0


def _in_payload(pid, path):
    """`path` as the payload process `pid` sees it: through its root, in its mount namespace."""
    return f"/proc/{pid}/root{path}"


def _shm_in_payload(pid, shmid):
    listing = run(["nsenter", "-t", str(pid), "-i", "cat", "/proc/sysvipc/shm"]).stdout
    return any(line.split()[1] == str(shmid) for line in listing.splitlines()[1:] if line.split())


def _namespaces_private(pid, left):
    """The epoch's own mount and IPC namespaces: its /tmp is another filesystem, and what the
    helper left there, file and SysV segment, is not on the host."""
    def namespace(of, kind):
        return os.readlink(f"/proc/{of}/ns/{kind}")
    try:
        return {"mount": namespace(pid, "mnt") != namespace("self", "mnt"),
                "ipc": namespace(pid, "ipc") != namespace("self", "ipc"),
                "tmp_is_its_own": os.stat(_in_payload(pid, "/tmp")).st_dev != os.stat("/tmp").st_dev,
                "file_not_on_host": os.path.exists(_in_payload(pid, left[0])) and not os.path.exists(left[0]),
                "segment_not_on_host": _shm_in_payload(pid, left[1]) and not _shm_exists(left[1])}
    except OSError as error:
        return {"error": str(error)}


def _payload_segment(uid):
    """A SysV shared memory segment made by `uid`, as a helper would leave one; its ID."""
    reader, writer = os.pipe()
    libc = ctypes.CDLL(None, use_errno=True)
    child = os.fork()
    if child == 0:
        try:
            os.close(reader)
            os.setgid(uid)
            os.setuid(uid)
            segment = libc.shmget(0, 4096, 0o1600)  # IPC_PRIVATE, IPC_CREAT | 0600
            os.write(writer, str(segment).encode())
            os._exit(0)
        except BaseException:  # reason: a forked child must never return into the harness
            os._exit(2)
    os.close(writer)
    data = os.read(reader, 32)
    os.close(reader)
    os.waitpid(child, 0)
    return int(data or b"-1")


def _staged_chain(top_dir, levels, uid):
    """A chain of `levels` directories owned by `uid` with 8 MiB at its bottom, under a fresh
    directory in `top_dir`; its top."""
    top = tempfile.mkdtemp(prefix="autocontrol-staged-deep-", dir=top_dir)
    path = top
    for _ in range(levels):
        path = os.path.join(path, "d")
        os.mkdir(path)
    with open(os.path.join(path, "pinned"), "wb") as handle:
        handle.write(bytes(8 << 20))
    for directory, subdirs, files in os.walk(top):
        for name in subdirs + files:
            os.lchown(os.path.join(directory, name), uid, uid)
    os.lchown(top, uid, uid)
    return top


def _shm_exists(shmid):
    with open("/proc/sysvipc/shm") as handle:
        return any(line.split()[1] == str(shmid) for line in handle.readlines()[1:])


def _as_payload():
    os.setgroups([])
    os.setresgid(PAYLOAD_BASE, PAYLOAD_BASE, PAYLOAD_BASE)
    os.setresuid(PAYLOAD_BASE, PAYLOAD_BASE, PAYLOAD_BASE)


def migration_denied(target_dir):
    result = subprocess.run(["/bin/sh", "-c", f"echo $$ > {target_dir}/cgroup.procs"], text=True,
                            capture_output=True, timeout=30, preexec_fn=_as_payload)
    return result.returncode != 0 and "Permission denied" in result.stderr


def escaped_in_payload(pid, epoch):
    if not isinstance(pid, int) or pid <= 0 or not pid_alive(pid):
        return False
    with open(f"/proc/{pid}/cgroup") as handle:
        path = handle.read().strip().partition("::")[2]
    return path.startswith(f"/autocontrol-test/{epoch}/records/") and path.endswith("/payload")


def _core_limit(pid):
    with open(f"/proc/{pid}/limits") as handle:
        for line in handle:
            if line.startswith("Max core file size"):
                return line.split()[4:6]
    return None


def session_inspection(epoch):
    processes = procs_under(f"{SUBTREE}/{epoch}")
    service = [(d, p) for d, p in processes if os.path.basename(d).startswith("service-")]
    payload = [(d, p) for d, p in processes if os.path.basename(d) == "payload"]
    return {"service": [status_of(p) for _d, p in service], "payload": [status_of(p) for _d, p in payload],
            "payload_pids": [p for _d, p in payload], "payload_cgroups": [d[len(SUBTREE):] for d, _p in payload]}


def scenario_session(steps):
    guardian = start_guardian()
    epoch = epochs()[-1]
    holder = client("hold")
    steps["request"] = read_json(holder)
    steps["inspection"] = session_inspection(epoch)
    steps["payload_core_limits"] = [_core_limit(p) for p in steps["inspection"]["payload_pids"]]
    probe = run([OPT + "/seccomp_probe"])
    steps["seccomp_probe"] = json.loads(probe.stdout or "{}")
    steps["payload_cannot_join_epoch"] = migration_denied(f"{SUBTREE}/{epoch}")
    steps["payload_cannot_join_records"] = migration_denied(f"{SUBTREE}/{epoch}/records")
    foreign = client("foreign", account="acother")
    steps["foreign_client"] = read_json(foreign)
    foreign.wait(timeout=30)
    steps["epoch_limits"] = {name: open(f"{SUBTREE}/{epoch}/records/{name}").read().strip()
                             for name in ("pids.max", "memory.max")}
    steps["epoch_bounds"] = {name: open(f"{SUBTREE}/{epoch}/{name}").read().strip()
                             for name in ("cgroup.max.depth", "cgroup.max.descendants", "pids.max", "memory.max")}
    steps["subtree_caps"] = {name: open(f"{SUBTREE}/{name}").read().strip() for name in ("pids.max", "memory.max")}
    container = os.path.dirname(SUBTREE + steps["inspection"]["payload_cgroups"][0])
    steps["limits"] = {name: open(os.path.join(container, name)).read().strip()
                       for name in ("pids.max", "memory.max")}
    holder.stdin.write("spawn\n")
    holder.stdin.flush()
    steps["spawn"] = read_json(holder)
    holder.stdin.write("umask\n")
    holder.stdin.flush()
    steps["umask"] = read_json(holder)
    holder.stdin.write("leftovers\n")
    holder.stdin.flush()
    steps["leftovers"] = read_json(holder)
    left = steps["leftovers"].get("reply") or ["", -1, "", "", ""]
    pids = steps["inspection"]["payload_pids"]
    seen = pids[0] if pids else 0
    # What the helper left lies in its epoch's private roots: seen through its own root.
    steps["leftovers_present"] = bool(seen) and os.path.exists(_in_payload(seen, left[0])) and _shm_in_payload(
        seen, left[1]) and os.path.exists(_in_payload(seen, left[2] + "/d" * 40 + "/bottom")) and os.path.isfile(
        _in_payload(seen, left[3] + "/d" * 300 + "/pinned"))
    steps["namespaces"] = _namespaces_private(seen, left) if seen else {}
    escaped = steps["request"].get("escaped")
    steps["escaped_in_payload_cgroup"] = escaped_in_payload(escaped, epoch)
    holder.stdin.write("close\n")
    holder.stdin.flush()
    steps["close"] = read_json(holder)
    holder.wait(timeout=30)
    steps["payload_gone_after_close"] = bool(pids) and not any(pid_alive(p) for p in pids)
    steps["escaped_gone_after_close"] = isinstance(escaped, int) and escaped > 0 and not pid_alive(escaped)
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()
    steps["endpoint_after_stop"] = os.path.exists(ENDPOINT)
    # A stop purges nothing: the next start purges every slice before it serves.
    steps["left"] = left


def scenario_siblings(steps, left=None):
    """Two clients, two leases, two payloads: closing one leaves the other serving. Its start
    purged what the session's helper left; what could not be removed is closed off: root's,
    mode 0, unreachable to every payload ID."""
    # Another user took quarantine-looking names first and a payload wrote into them: names
    # mean nothing to the purge, so what the payload left there goes like anything else.
    squats = []
    for top in ("/var/tmp", "/dev/shm"):
        for suffix in ("", "-0000000000000000"):
            squat = f"{top}/.autocontrol-owner-quarantine{suffix}"
            if os.path.lexists(squat):
                continue
            os.mkdir(squat)
            os.chown(squat, 65534, 65534)
            os.chmod(squat, 0o1777)
            hidden = os.path.join(squat, "hidden")
            with open(hidden, "w") as handle:
                handle.write("payload")
            os.chown(hidden, PAYLOAD_BASE, PAYLOAD_BASE)
            squats.append(squat)
    # Another user's static tree, larger than the deferral room at the depth bound: it makes
    # the purge slower and log, never incomplete, so every slice is still handed out.
    static = tempfile.mkdtemp(prefix="autocontrol-static-", dir="/var/tmp")
    chain = os.path.join(static, *(["s"] * 62))  # Its 5000 children sit at the depth bound.
    os.makedirs(chain)
    for index in range(5000):
        os.mkdir(os.path.join(chain, f"w{index}"))
    for directory, subdirs, files in os.walk(static):
        os.chown(directory, 65534, 65534)
    looped = tempfile.mkdtemp(prefix="autocontrol-loop-", dir="/var/tmp")
    os.mkdir(os.path.join(looped, "inner"))
    steps["loop_mounted"] = run(["mount", "--bind", looped, os.path.join(looped, "inner")]).returncode == 0
    # A directory from outside every root, holding a payload-owned file, mounted under a root:
    # the purge must not reach through the mount and remove it.
    outside = tempfile.mkdtemp(prefix="autocontrol-outside-", dir="/root")
    kept = os.path.join(outside, "kept")
    with open(kept, "w") as handle:
        handle.write("outside the purge roots")
    os.chown(kept, PAYLOAD_BASE, PAYLOAD_BASE)
    window = tempfile.mkdtemp(prefix="autocontrol-window-", dir="/var/tmp")
    steps["outside_mounted"] = run(["mount", "--bind", outside, window]).returncode == 0
    # A payload directory holding a payload file, covered by another user's mount (a tmpfs
    # here, as a FUSE mount would be): the purge lays it bare in its own namespace.
    covered = tempfile.mkdtemp(prefix="autocontrol-covered-", dir="/var/tmp")
    with open(os.path.join(covered, "hidden"), "w") as handle:
        handle.write("payload data")
    os.chown(os.path.join(covered, "hidden"), PAYLOAD_BASE, PAYLOAD_BASE)
    os.chown(covered, PAYLOAD_BASE, PAYLOAD_BASE)
    steps["cover_mounted"] = run(["mount", "-t", "tmpfs", "-o", "size=1m", "cover", covered]).returncode == 0
    # The same with another user's dead FUSE mount, which refuses root a getattr; and one such
    # mount on that user's own directory, which every purge meets and must not stop at.
    fuse_covered = tempfile.mkdtemp(prefix="autocontrol-fuse-covered-", dir="/var/tmp")
    with open(os.path.join(fuse_covered, "hidden"), "w") as handle:
        handle.write("payload data")
    os.chown(os.path.join(fuse_covered, "hidden"), PAYLOAD_BASE, PAYLOAD_BASE)
    os.chown(fuse_covered, PAYLOAD_BASE, PAYLOAD_BASE)
    fuse_static = tempfile.mkdtemp(prefix="autocontrol-fuse-static-", dir="/tmp")
    os.chown(fuse_static, 65534, 65534)
    steps["fuse_mounted"] = _dead_fuse_mount(fuse_covered, 65534) and _dead_fuse_mount(fuse_static, 65534)
    # And with a FUSE mount whose root inode went bad: every getattr on it fails with EIO.
    fuse_bad = tempfile.mkdtemp(prefix="autocontrol-fuse-bad-", dir="/var/tmp")
    with open(os.path.join(fuse_bad, "hidden"), "w") as handle:
        handle.write("payload data")
    os.chown(os.path.join(fuse_bad, "hidden"), PAYLOAD_BASE, PAYLOAD_BASE)
    os.chown(fuse_bad, PAYLOAD_BASE, PAYLOAD_BASE)
    steps["bad_fuse_mounted"] = _bad_fuse_mount(fuse_bad, 65534)
    # A crash report a payload left in /var/crash (apport writes them owned by the crashing UID).
    crash_made = not os.path.isdir("/var/crash")
    if crash_made:
        os.mkdir("/var/crash", 0o3777)
        os.chmod("/var/crash", 0o3777)
    crash_report = "/var/crash/_usr_bin_python3.%d.crash" % PAYLOAD_BASE
    with open(crash_report, "w") as handle:
        handle.write("CoreDump: base64")
    os.chown(crash_report, PAYLOAD_BASE, PAYLOAD_BASE)
    # A message queue the payload left: purged though this host has no /dev/mqueue mounted.
    steps["queue_made"] = _payload_queue(PAYLOAD_BASE)
    # And one of another ID's, which stays.
    steps["foreign_queue_made"] = _payload_queue(65534, b"/autocontrol-foreign-queue")
    # What a helper could leave on the host, staged here: a file, a SysV segment, a 300-level
    # chain with 8 MiB at its bottom, and a directory another ID wrote into.
    staged_file = os.path.join(tempfile.mkdtemp(prefix="autocontrol-staged-", dir="/tmp"), "left")
    open(staged_file, "w").close()
    os.chown(staged_file, PAYLOAD_BASE, PAYLOAD_BASE)
    staged_segment = _payload_segment(PAYLOAD_BASE)
    staged_chain = _staged_chain("/dev/shm", 300, PAYLOAD_BASE)
    staged_shared = tempfile.mkdtemp(prefix="autocontrol-staged-shared-", dir="/tmp")
    os.chmod(staged_shared, 0o777)
    os.chown(staged_shared, PAYLOAD_BASE, PAYLOAD_BASE)
    open(os.path.join(staged_shared, "foreign"), "w").close()  # Another ID's file inside it.
    steps["staged"] = {"segment": staged_segment, "present": os.path.exists(staged_file) and _shm_exists(
        staged_segment) and os.path.isfile(staged_chain + "/d" * 300 + "/pinned")}
    guardian = start_guardian()
    steps["squats"] = squats
    steps["squatted_payload_files_left"] = [s for s in squats if os.path.lexists(os.path.join(s, "hidden"))]
    steps["crash_report_left"] = os.path.lexists(crash_report)  # Right after the startup purge.
    for squat in squats:
        shutil.rmtree(squat, ignore_errors=True)
    steps["leftovers_after_start"] = os.path.exists(staged_file) or _shm_exists(staged_segment)
    # The 300-level chain (8 MiB at its bottom) and the directory another ID wrote into: their
    # names are free and nothing a payload ID owns is left anywhere under the purge roots.
    steps["names_freed"] = not os.path.lexists(staged_chain) and not os.path.lexists(staged_shared)
    shutil.rmtree(os.path.dirname(staged_file), ignore_errors=True)
    # The window shows a directory outside every root: what is there is not the purge's.
    steps["payload_owned_left"] = [p for p in payload_owned_anywhere() if not p.startswith(window + "/")]
    first, second = client("hold"), client("hold")
    steps["first"], steps["second"] = read_json(first), read_json(second)
    epoch = epochs()[-1]
    steps["payload_uids"] = sorted({status["uid"] for status in session_inspection(epoch)["payload"]})
    first_escaped, second_escaped = steps["first"].get("escaped"), steps["second"].get("escaped")
    first.stdin.write("close\n")
    first.stdin.flush()
    steps["first_close"] = read_json(first)
    first.wait(timeout=30)
    steps["first_escaped_gone"] = isinstance(first_escaped, int) and not pid_alive(first_escaped)
    steps["second_escaped_alive"] = isinstance(second_escaped, int) and pid_alive(second_escaped)
    second.stdin.write("ping\n")
    second.stdin.flush()
    steps["second_after_sibling_close"] = read_json(second)
    second.stdin.write("close\n")
    second.stdin.flush()
    steps["second_close"] = read_json(second)
    second.wait(timeout=30)
    steps["second_escaped_gone"] = isinstance(second_escaped, int) and not pid_alive(second_escaped)
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()
    steps["static_tree_logged"] = "unwalked" in steps["guardian_stop"][1]
    with open("/proc/sys/kernel/core_pattern") as handle:
        pattern = handle.read().rstrip("\n")
    handler = os.path.basename(pattern[1:].split()[0]) if pattern.startswith("|") and pattern[1:].split() else ""
    steps["core_pattern_warning_expected"] = pattern.startswith("@") or (
        pattern.startswith("|") and handler not in ("systemd-coredump", "apport"))
    steps["core_pattern_warned"] = "core_pattern" in steps["guardian_stop"][1]
    # The 300-level chain went in the startup purge without meeting churn.
    steps["churn_logged"] = "met churn" in steps["guardian_stop"][1]
    # The bind loop was detached in the purge's own namespace, not met again as a directory.
    steps["revisit_logged"] = "met a directory again" in steps["guardian_stop"][1]
    steps["outside_file_kept"] = os.path.exists(kept)
    # The purge detached mounts only in its own namespace: the host still has both.
    with open("/proc/self/mountinfo") as handle:
        points = {line.split()[4] for line in handle}
    steps["host_mounts_kept"] = window in points and os.path.join(looped, "inner") in points \
        and fuse_static in points
    run(["umount", "-l", fuse_covered])
    run(["umount", "-l", fuse_static])
    steps["fuse_covered_payload_left"] = os.path.lexists(os.path.join(fuse_covered, "hidden"))
    steps["queue_left"] = _queue_exists()
    try:
        os.unlink(crash_report)
    except FileNotFoundError:
        pass
    if crash_made:
        shutil.rmtree("/var/crash", ignore_errors=True)
    steps["foreign_queue_kept"] = _queue_exists(b"/autocontrol-foreign-queue")
    run(["umount", "-l", fuse_bad])
    steps["bad_fuse_payload_left"] = os.path.lexists(os.path.join(fuse_bad, "hidden"))
    shutil.rmtree(fuse_bad, ignore_errors=True)
    shutil.rmtree(fuse_covered, ignore_errors=True)
    shutil.rmtree(fuse_static, ignore_errors=True)
    run(["umount", "-l", covered])
    steps["covered_payload_left"] = os.path.lexists(covered)
    shutil.rmtree(covered, ignore_errors=True)
    run(["umount", "-l", window])
    shutil.rmtree(window, ignore_errors=True)
    shutil.rmtree(outside, ignore_errors=True)
    shutil.rmtree(static, ignore_errors=True)
    run(["umount", "-l", os.path.join(looped, "inner")])
    shutil.rmtree(looped, ignore_errors=True)


def scenario_nested(steps):
    """A protected parent opens a child lease with its delivered grant and starts a child."""
    guardian = start_guardian()
    epoch = epochs()[-1]
    driver = client("nested")
    steps["nest"] = read_json(driver)
    escaped = (steps["nest"].get("result") or {}).get("escaped")
    paths = [d[len(SUBTREE):] for d, _p in procs_under(f"{SUBTREE}/{epoch}") if os.path.basename(d) == "payload"]
    steps["payload_cgroups"] = paths
    steps["child_cgroup"] = None
    if isinstance(escaped, int) and pid_alive(escaped):
        with open(f"/proc/{escaped}/cgroup") as handle:
            steps["child_cgroup"] = handle.read().strip().partition("::")[2]
    driver.stdin.write("\n")
    driver.stdin.flush()
    steps["close_child"] = read_json(driver)
    steps["child_escaped_gone"] = isinstance(escaped, int) and not pid_alive(escaped)
    driver.stdin.write("\n")
    driver.stdin.flush()
    steps["close"] = read_json(driver)
    driver.wait(timeout=60)
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()


def scenario_race(steps):
    """Revoke racing launch: every cycle retires and no payload survives."""
    guardian = start_guardian()
    epoch = epochs()[-1]
    driver = client("race")
    steps["race"] = read_json(driver)
    driver.wait(timeout=120)
    time.sleep(0.3)
    steps["payloads_left"] = [p for d, p in procs_under(f"{SUBTREE}/{epoch}") if os.path.basename(d) == "payload"]
    records = f"{SUBTREE}/{epoch}/records"
    names = os.listdir(records) if os.path.isdir(records) else []
    steps["containers_left"] = sorted(n for n in names if n.startswith("r-"))
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()


def scenario_renewal(steps):
    """An idle channel outlives several lease lifetimes (4 s) because the client renews."""
    guardian = start_guardian()
    holder = client("hold")
    steps["request"] = read_json(holder)
    time.sleep(12)
    holder.stdin.write("ping\n")
    holder.stdin.flush()
    steps["ping_after_idle"] = read_json(holder)
    holder.stdin.write("close\n")
    holder.stdin.flush()
    steps["close"] = read_json(holder)
    holder.wait(timeout=30)
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()


def _all_children(pid):
    kids = []
    for task in os.listdir(f"/proc/{pid}/task"):
        with open(f"/proc/{pid}/task/{task}/children") as handle:
            kids += [int(value) for value in handle.read().split()]
    return kids


def _comm(pid):
    try:
        with open(f"/proc/{pid}/comm") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def children_of(pid):
    """Every child of `pid`, zombies included: a zombie stays a child until it is reaped.
    Purge children (forks of the guardian) are short-lived: waited out first, so any child
    left over, purge or service, counts."""
    limit = time.monotonic() + 30
    while time.monotonic() < limit and any(_comm(kid) != "service_main" for kid in _all_children(pid)):
        time.sleep(0.1)
    return _all_children(pid)


def rollover_session():
    """One full session; retried while the guardian is between epochs."""
    for attempt in range(1, 41):
        holder = client("hold")
        try:
            reply = json.loads(holder.stdout.readline() or "{}")
        except ValueError:
            reply = {}
        if reply.get("reply") == "pong":
            epoch = epochs()
            uids = payload_uids(epoch[-1])
            holder.stdin.write("close\n")
            holder.stdin.flush()
            closed = read_json(holder)
            holder.wait(timeout=30)
            return {"attempts": attempt, "epochs": epoch, "uids": uids, "retired": closed.get("retired") is True}
        holder.kill()
        holder.wait()
        time.sleep(0.25)
    return {"attempts": 40, "retired": False}


def scenario_rollover(steps):
    """Spending the quota drains the epoch; the same guardian grants the next one."""
    guardian = start_guardian()
    steps["sessions"] = [rollover_session() for _ in range(ROLLOVER_SESSIONS)]
    steps["guardian_alive"] = guardian.poll() is None
    steps["guardian_children"] = children_of(guardian.pid)
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()


def payload_uids(epoch):
    return sorted({status["uid"] for status in session_inspection(epoch)["payload"]})


def scenario_long_lived(steps):
    """A helper that outlives its epoch's quota: the next epoch starts beside it, it keeps
    serving, and its epoch is reclaimed only when it closes."""
    guardian = start_guardian()
    first = epochs()[-1]
    holder = client("hold")
    steps["holder"] = read_json(holder)
    steps["holder_uids"] = payload_uids(first)
    steps["sessions"] = [rollover_session() for _ in range(ROLLOVER_SESSIONS)]
    steps["epochs_while_held"] = epochs()
    # Helpers that ran in the successor epoch, recorded by each session while it was open.
    steps["successor_uids"] = sorted({uid for s in steps["sessions"] if len(s.get("epochs", [])) == 2
                                      for uid in s.get("uids", [])})
    holder.stdin.write("ping\n")
    holder.stdin.flush()
    steps["holder_ping"] = read_json(holder)
    holder.stdin.write("close\n")
    holder.stdin.flush()
    steps["holder_close"] = read_json(holder)
    holder.wait(timeout=30)
    limit = time.monotonic() + 20
    while first in epochs() and time.monotonic() < limit:
        time.sleep(0.1)
    steps["first_reclaimed"] = first not in epochs()
    steps["guardian_children"] = children_of(guardian.pid)
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()


def scenario_service_crash(steps):
    """The service dies mid-session, as a drain past its deadline exits: the live guardian
    reclaims the whole epoch, helper and escaped descendant included, and serves the next."""
    guardian = start_guardian()
    epoch = epochs()[-1]
    holder = client("hold")
    steps["request"] = read_json(holder)
    escaped = steps["request"].get("escaped")
    processes = procs_under(f"{SUBTREE}/{epoch}")
    payloads = [p for d, p in processes if os.path.basename(d) == "payload"]
    service = [p for d, p in processes if os.path.basename(d).startswith("service-")]
    os.kill(service[0], signal.SIGKILL)
    limit = time.monotonic() + 20
    while time.monotonic() < limit and (epoch in epochs() or not epochs()):
        time.sleep(0.1)
    steps["old_epoch_gone"] = epoch not in epochs()
    steps["payload_gone"] = bool(payloads) and not any(pid_alive(p) for p in payloads)
    steps["escaped_gone"] = isinstance(escaped, int) and escaped > 0 and not pid_alive(escaped)
    holder.kill()
    holder.wait()
    steps["guardian_alive"] = guardian.poll() is None
    steps["next_session"] = rollover_session()
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()


def scenario_worker(steps):
    """The template's helper program, the package's native worker, runs under the service."""
    guardian = start_guardian()
    epoch = epochs()[-1]
    driver = client("worker")
    steps["bootstrap"] = read_json(driver)
    steps["inspection"] = session_inspection(epoch)
    driver.stdin.write("\n")
    driver.stdin.flush()
    steps["close"] = read_json(driver)
    driver.wait(timeout=60)
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()


def scenario_second_overlap(steps):
    """Two overlaps in a row. E1 retires around H1; E2 drains on its own while E1 still
    retires, and E3 must not take H1's half or purge H1's files. Then E3 retires around H3
    while E1 still does: that handover waits, and happens once E1 is reclaimed. A guardian
    limited to one retiring epoch makes that wait."""
    guardian = start_guardian("guardian_one_retiring")
    first = epochs()[-1]
    h1 = client("hold")
    steps["h1"] = read_json(h1)
    h1.stdin.write("leftovers\n")
    h1.stdin.flush()
    left = (read_json(h1).get("reply") or ["", -1, ""])
    steps["h1_uids"] = payload_uids(first)
    h1_pids = session_inspection(first)["payload_pids"]
    h1_seen = h1_pids[0] if h1_pids else 0
    steps["fill_first"] = [rollover_session() for _ in range(7)]       # E1 spent around H1: retires.
    steps["fill_second"] = [rollover_session() for _ in range(8)]      # E2 spent and idle: drains.
    steps["third"] = rollover_session()                                # Lands in E3.
    steps["h1_files_kept"] = bool(h1_seen) and os.path.exists(_in_payload(h1_seen, left[0])) and os.path.exists(
        _in_payload(h1_seen, left[2]))
    h3 = client("hold")
    steps["h3"] = read_json(h3)
    steps["fill_third"] = [rollover_session() for _ in range(6)]       # E3 spent around H3, E1 still retiring.
    steps["epochs_pending"] = epochs()
    h1.stdin.write("close\n")
    h1.stdin.flush()
    steps["h1_close"] = read_json(h1)
    h1.wait(timeout=30)
    # The guardian removes the epoch's branch, then purges its half: wait for both.
    limit = time.monotonic() + 20
    while first in epochs() and time.monotonic() < limit:
        time.sleep(0.1)
    # Its namespace went with it: the files were never on the host and no process holds them.
    steps["h1_files_purged"] = first not in epochs() and not pid_alive(h1_seen) and not os.path.exists(left[0])
    steps["fourth"] = rollover_session()                               # The pending handover: E4.
    steps["epochs_after_handover"] = epochs()
    h3.stdin.write("close\n")
    h3.stdin.flush()
    steps["h3_close"] = read_json(h3)
    h3.wait(timeout=30)
    limit = time.monotonic() + 20
    while len(epochs()) > 1 and time.monotonic() < limit:
        time.sleep(0.1)
    steps["guardian_children"] = children_of(guardian.pid)
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()


def scenario_triple_overlap(steps):
    """Two long-lived helpers keep two spent epochs retiring while a third serves: three
    epochs at once, on three slices."""
    guardian = start_guardian()
    first = epochs()[-1]
    h1 = client("hold")
    steps["h1"] = read_json(h1)
    steps["h1_uids"] = payload_uids(first)
    steps["fill_first"] = [rollover_session() for _ in range(7)]       # E1 retires around H1.
    second = epochs()[-1]
    h2 = client("hold")
    steps["h2"] = read_json(h2)
    steps["h2_uids"] = payload_uids(second)
    steps["fill_second"] = [rollover_session() for _ in range(7)]      # E2 spent around H2: retires.
    steps["third"] = rollover_session()                                # Lands in E3.
    third = epochs()[-1]
    h3 = client("hold")
    steps["h3"] = read_json(h3)
    steps["h3_uids"] = payload_uids(third)
    steps["fill_third"] = [rollover_session() for _ in range(6)]       # E3 spent around H3: retires.
    steps["fourth"] = rollover_session()                               # Lands in E4: all four slices.
    steps["epochs_held"] = epochs()
    holders = (h1, h2, h3)
    for holder in holders:
        holder.stdin.write("ping\n")
        holder.stdin.flush()
    steps["pings"] = [read_json(holder) for holder in holders]
    for holder in holders:
        holder.stdin.write("close\n")
        holder.stdin.flush()
    steps["closes"] = [read_json(holder) for holder in holders]
    for holder in holders:
        holder.wait(timeout=30)
    limit = time.monotonic() + 20
    while len(epochs()) > 1 and time.monotonic() < limit:
        time.sleep(0.1)
    steps["guardian_children"] = children_of(guardian.pid)
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()


def scenario_retiring_nested(steps):
    """A nested parent whose epoch retired still opens a child: its connection goes to the
    epoch running its slice, not to the current one."""
    guardian = start_guardian()
    first = epochs()[-1]
    driver = client("nested_later")
    steps["started"] = read_json(driver)
    steps["parent_uids"] = payload_uids(first)
    steps["fill"] = [rollover_session() for _ in range(7)]             # The parent's epoch retires.
    steps["epochs_before_nest"] = epochs()
    driver.stdin.write("\n")
    driver.stdin.flush()
    steps["nest"] = read_json(driver)
    escaped = (steps["nest"].get("result") or {}).get("escaped")
    steps["child_uid"] = status_of(escaped)["uid"] if isinstance(escaped, int) and pid_alive(escaped) else None
    for stage in ("close_child", "close"):
        driver.stdin.write("\n")
        driver.stdin.flush()
        steps[stage] = read_json(driver)
    driver.wait(timeout=60)
    steps["guardian_stop"] = stop_guardian(guardian)


def _cpu_ticks(pid):
    with open(f"/proc/{pid}/stat") as handle:
        fields = handle.read().rsplit(")", 1)[1].split()
    return int(fields[11]) + int(fields[12])


def _block_new_cgroups(blocked):
    """No new cgroup anywhere below the subtree; the ones there stay (the limit counts live ones)."""
    with open(f"{SUBTREE}/cgroup.max.descendants", "w") as handle:
        handle.write("0" if blocked else "max")


def _kill_current_service():
    epoch = epochs()[-1]
    service = [p for d, p in procs_under(f"{SUBTREE}/{epoch}") if os.path.basename(d).startswith("service-")]
    os.kill(service[0], signal.SIGKILL)
    return epoch


def scenario_restart_backoff(steps):
    """A next epoch that cannot be created is retried from the main loop with a growing
    backoff: the guardian stays idle, serves again once creation works, and answers SIGTERM
    at once while it waits."""
    guardian = start_guardian()
    try:
        time.sleep(1.2)                                        # A run of over a second: not a crash.
        _block_new_cgroups(True)
        ended = _kill_current_service()
        time.sleep(1.5)
        before = _cpu_ticks(guardian.pid)
        time.sleep(3)
        steps["cpu_ticks_while_blocked"] = _cpu_ticks(guardian.pid) - before
        steps["epochs_while_blocked"] = epochs()
        steps["old_epoch_gone"] = ended not in epochs()
        steps["alive_while_blocked"] = guardian.poll() is None
        _block_new_cgroups(False)
        limit = time.monotonic() + 45
        while time.monotonic() < limit and not epochs():
            time.sleep(0.2)
        steps["epochs_after_unblock"] = epochs()
        steps["next_session"] = rollover_session()
        time.sleep(1.2)
        _block_new_cgroups(True)
        _kill_current_service()
        time.sleep(1.5)
        started = time.monotonic()
        steps["guardian_stop"] = stop_guardian(guardian)
        steps["stop_seconds"] = round(time.monotonic() - started, 2)
    finally:
        _block_new_cgroups(False)
        if guardian.poll() is None:
            stop_guardian(guardian)
    steps["epochs_after_stop"] = epochs()


def scenario_purge_faults(steps):
    """The purge's fault paths (a failed listing, a mount placed during the walk, a directory
    renamed behind it, the mount API refused three ways) and the manifest's purge-root checks
    that only root can stage."""
    faults = run([OPT + "/purge_fault"])
    steps["faults"] = json.loads(faults.stdout or "{}")
    steps["faults_exit"] = faults.returncode
    roots = run([OPT + "/purge_roots_check"])
    steps["roots"] = json.loads(roots.stdout or "{}")
    steps["roots_exit"] = roots.returncode


_OUTSIDE_EPOCH = """
import socket, sys
peer = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
peer.settimeout(10)
try:
    peer.connect(sys.argv[1])
except OSError as error:
    print("connect:" + type(error).__name__)
    sys.exit(0)
try:
    peer.send(b"x" * 64)
    print("reply:" + str(len(peer.recv(4096))))
except OSError as error:
    print("closed:" + type(error).__name__)
"""


def scenario_outside_epoch(steps):
    """A process with a payload ID that is not in any epoch's own mount namespace (here: on
    the host) is turned away by the guardian before any service sees it."""
    guardian = start_guardian()
    probe = subprocess.run(["/usr/bin/python3", "-I", "-c", _OUTSIDE_EPOCH, ENDPOINT], preexec_fn=_as_payload,
                           capture_output=True, text=True, timeout=30)
    steps["outcome"] = probe.stdout.strip()
    steps["guardian_stop"] = stop_guardian(guardian)


def scenario_taken_range(steps):
    """A manifest whose payload range holds a real account is refused before anything starts."""
    refused = run([OPT + "/guardian_taken_range"], timeout=30)
    steps["refused"] = [refused.returncode, refused.stderr.strip()[-200:]]
    steps["epochs"] = epochs()


def scenario_remote(steps):
    """A remote helper under the service: negotiation through the relay as a payload ID."""
    guardian = start_guardian()
    epoch = epochs()[-1]
    driver = client("remote")
    steps["negotiate"] = read_json(driver)
    steps["inspection"] = session_inspection(epoch)
    driver.stdin.write("\n")
    driver.stdin.flush()
    steps["close"] = read_json(driver)
    driver.wait(timeout=60)
    steps["guardian_stop"] = stop_guardian(guardian)


def scenario_delegated_subtree(steps):
    """A guardian whose subtree sits below a delegated cgroup refuses; once root owns that
    cgroup again it starts."""
    os.makedirs(OUTER + "/inner")
    os.makedirs(STATE2, mode=0o700)
    with open(OUTER + "/cgroup.subtree_control", "w") as handle:
        handle.write("+pids +memory")
    other = pwd.getpwnam("acother")
    os.chown(OUTER + "/cgroup.procs", other.pw_uid, other.pw_gid)
    refused = run([OPT + "/guardian_outer"], timeout=30)
    steps["delegated_refused"] = [refused.returncode, refused.stderr.strip()[-200:]]
    os.chown(OUTER + "/cgroup.procs", 0, 0)
    guardian = subprocess.Popen([OPT + "/guardian_outer"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env={})
    limit = time.monotonic() + 15
    while not os.path.exists(ENDPOINT) and time.monotonic() < limit and guardian.poll() is None:
        time.sleep(0.05)
    steps["trusted_started"] = os.path.exists(ENDPOINT)
    steps["guardian_stop"] = stop_guardian(guardian)
    steps["epochs_after_stop"] = [n for n in os.listdir(OUTER + "/inner") if n.startswith("epoch-")]


def _freeze(cgroup, frozen):
    """Freezes or thaws a cgroup and waits until the kernel says it is done."""
    with open(f"{cgroup}/cgroup.freeze", "w") as handle:
        handle.write("1" if frozen else "0")
    limit = time.monotonic() + 10
    while time.monotonic() < limit:
        with open(f"{cgroup}/cgroup.events") as handle:
            if f"frozen {int(frozen)}" in handle.read():
                return True
        time.sleep(0.05)
    return False


def scenario_cold_recovery(steps):
    guardian = start_guardian()
    epoch = epochs()[-1]
    holder = client("hold")
    steps["request"] = read_json(holder)
    inspection = session_inspection(epoch)
    steps["payload_pids"] = inspection["payload_pids"]
    escaped = steps["request"].get("escaped")
    steps["escaped_in_payload_cgroup"] = escaped_in_payload(escaped, epoch)
    # Frozen first: a service that saw its guardian go would drain and kill its helpers before
    # the crash below is complete. SIGKILL still reaches frozen tasks.
    steps["epoch_frozen"] = _freeze(f"{SUBTREE}/{epoch}", True)
    os.kill(guardian.pid, signal.SIGKILL)
    guardian.wait()
    for directory, pid in procs_under(f"{SUBTREE}/{epoch}"):
        if os.path.basename(directory).startswith("service-"):
            os.kill(pid, signal.SIGKILL)
    steps["epoch_thawed"] = _freeze(f"{SUBTREE}/{epoch}", False)
    time.sleep(0.5)
    steps["payload_alive_after_crash"] = any(pid_alive(p) for p in inspection["payload_pids"])
    steps["escaped_alive_after_crash"] = isinstance(escaped, int) and pid_alive(escaped)
    steps["epochs_after_crash"] = epochs()
    holder.stdin.close()
    holder.kill()
    holder.wait()
    if os.path.exists(ENDPOINT):
        os.unlink(ENDPOINT)  # A crashed guardian leaves its socket; the next one replaces only a socket.
    restarted = start_guardian(ignore_sigchld=True)  # Its own reset must still let it wait for purges.
    steps["epochs_after_restart"] = epochs()
    steps["payload_gone_after_recovery"] = not any(pid_alive(p) for p in inspection["payload_pids"])
    steps["escaped_gone_after_recovery"] = isinstance(escaped, int) and not pid_alive(escaped)
    steps["guardian_stop"] = stop_guardian(restarted)
    steps["epochs_after_stop"] = epochs()


def remove_cgroups(path):
    if not os.path.isdir(path):
        return
    try:
        with open(os.path.join(path, "cgroup.kill"), "w") as handle:
            handle.write("1")
    except OSError:
        pass
    time.sleep(0.2)
    for directory, subdirs, _files in sorted(os.walk(path), key=lambda item: -item[0].count("/")):
        for name in subdirs:
            try:
                os.rmdir(os.path.join(directory, name))
            except OSError:
                pass
    os.rmdir(path)


def cleanup():
    leftovers = {}
    run(["pkill", "-KILL", "-f", OPT + "/guardian"])
    try:
        remove_cgroups(SUBTREE)
    except OSError as error:
        leftovers["cgroup"] = str(error)
    if os.path.exists(OUTER):
        try:
            remove_cgroups(OUTER)
        except OSError as error:
            leftovers["outer_cgroup"] = str(error)
    for path in (STATE, STATE2, RUN, OPT):
        shutil.rmtree(path, ignore_errors=True)
    for name in created_accounts:
        result = run(["userdel", name])
        if result.returncode:
            leftovers[name] = result.stderr
    run(["gpasswd", "--delete", CLIENT, SOCKET_GROUP])
    for controller in enabled_controllers:
        try:
            with open(ROOT_CONTROL, "w") as handle:
                handle.write("-" + controller)
        except OSError as error:
            leftovers["controller_" + controller] = str(error)
    for name in created_groups:
        result = run(["groupdel", name])
        if result.returncode:
            leftovers[name] = result.stderr
    report["cleanup"] = {"leftovers": leftovers, "subtree_exists": os.path.exists(SUBTREE),
                         "accounts_present": [n for n in ACCOUNTS if _exists(n)],
                         "groups_present": [n for n in (*ACCOUNTS, SOCKET_GROUP) if _group_exists(n)],
                         "client_in_socket_group": _member(CLIENT, SOCKET_GROUP)}


def _group_exists(name):
    try:
        grp.getgrnam(name)
        return True
    except KeyError:
        return False


def _member(user, group):
    try:
        return user in grp.getgrnam(group).gr_mem
    except KeyError:
        return False


def _exists(name):
    try:
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


def main():
    if os.geteuid() != 0:
        raise SystemExit("protected acceptance runs as root inside the WSL distro only")
    try:
        provision()
        build()
        report["steps"]["session"] = {}
        scenario_session(report["steps"]["session"])
        report["steps"]["siblings"] = {}
        scenario_siblings(report["steps"]["siblings"], report["steps"]["session"].get("left"))
        report["steps"]["nested"] = {}
        scenario_nested(report["steps"]["nested"])
        report["steps"]["race"] = {}
        scenario_race(report["steps"]["race"])
        report["steps"]["cold_recovery"] = {}
        scenario_cold_recovery(report["steps"]["cold_recovery"])
        report["steps"]["renewal"] = {}
        scenario_renewal(report["steps"]["renewal"])
        report["steps"]["rollover"] = {}
        scenario_rollover(report["steps"]["rollover"])
        report["steps"]["service_crash"] = {}
        scenario_service_crash(report["steps"]["service_crash"])
        report["steps"]["delegated_subtree"] = {}
        scenario_delegated_subtree(report["steps"]["delegated_subtree"])
        report["steps"]["worker"] = {}
        scenario_worker(report["steps"]["worker"])
        report["steps"]["long_lived"] = {}
        scenario_long_lived(report["steps"]["long_lived"])
        report["steps"]["second_overlap"] = {}
        scenario_second_overlap(report["steps"]["second_overlap"])
        report["steps"]["taken_range"] = {}
        scenario_taken_range(report["steps"]["taken_range"])
        report["steps"]["triple_overlap"] = {}
        scenario_triple_overlap(report["steps"]["triple_overlap"])
        report["steps"]["remote"] = {}
        scenario_remote(report["steps"]["remote"])
        report["steps"]["retiring_nested"] = {}
        scenario_retiring_nested(report["steps"]["retiring_nested"])
        report["steps"]["restart_backoff"] = {}
        scenario_restart_backoff(report["steps"]["restart_backoff"])
        report["steps"]["purge_faults"] = {}
        scenario_purge_faults(report["steps"]["purge_faults"])
        report["steps"]["outside_epoch"] = {}
        scenario_outside_epoch(report["steps"]["outside_epoch"])
    except Exception as error:  # reason: cleanup must run and the failure must be reported, not lost
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        cleanup()
    report["expectations"] = expectations(report)
    print(json.dumps(report))
    raise SystemExit(0 if report["expectations"] and all(report["expectations"].values()) else 1)


def slice_of(uids):
    """The payload slice all of `uids` lie in, or None if empty or mixed."""
    halves = {(int(u) - PAYLOAD_BASE) // EPOCH_IDS for u in uids or []}
    return halves.pop() if len(halves) == 1 else None


def in_payload_range(value):
    return isinstance(value, str) and value.isdigit() and 0 <= int(value) - PAYLOAD_BASE < PAYLOAD_IDS


def child_inside_parent(nested):
    """The child's payload cgroup is a record container inside the parent's container."""
    child = nested.get("child_cgroup")
    if not isinstance(child, str) or not child.startswith("/autocontrol-test/"):
        return False
    child = child[len("/autocontrol-test"):]
    parent = min(nested["payload_cgroups"], key=lambda path: path.count("/"))
    container = parent[:-len("/payload")]
    return child.endswith("/payload") and child.startswith(container + "/r-") and child != parent


def expectations(result):
    session = result["steps"].get("session", {})
    crash = result["steps"].get("cold_recovery", {})
    siblings = result["steps"].get("siblings", {})
    nested = result["steps"].get("nested", {})
    race = result["steps"].get("race", {})
    renewal = result["steps"].get("renewal", {})
    rollover = result["steps"].get("rollover", {})
    service_crash = result["steps"].get("service_crash", {})
    delegated = result["steps"].get("delegated_subtree", {})
    worker = result["steps"].get("worker", {})
    held = result["steps"].get("long_lived", {})
    second = result["steps"].get("second_overlap", {})
    taken = result["steps"].get("taken_range", {})
    triple = result["steps"].get("triple_overlap", {})
    remote = result["steps"].get("remote", {})
    retiring_nested = result["steps"].get("retiring_nested", {})
    restart = result["steps"].get("restart_backoff", {})
    faults = result["steps"].get("purge_faults", {})
    outside = result["steps"].get("outside_epoch", {})
    inspection = session.get("inspection", {})
    service, payload = inspection.get("service", [{}]), inspection.get("payload", [{}])
    if "error" in result or not all((session, crash, siblings, nested, race, renewal, rollover, service_crash,
                                     delegated, worker, held, second, taken, triple, remote, retiring_nested,
                                     restart, faults, outside)):
        return {"completed": False}
    return {
        "protected_reply": session["request"].get("reply") == "pong",
        # Exactly CAP_SETUID, CAP_SETGID and CAP_SETPCAP, as the service account.
        "service_account_and_capabilities": service[0].get("uid") == str(result["accounts"]["SERVICE_UID"])
        and service[0].get("cap_eff") == "00000000000001c0",
        # A code-execution bug in the service cannot regain more than those three.
        "service_bounding_set_and_no_new_privs": service[0].get("cap_bnd") == "00000000000001c0"
        and service[0].get("no_new_privs") == "1",
        "payload_account_without_capabilities": in_payload_range(payload[0].get("uid"))
        and payload[0].get("cap_eff") == "0000000000000000" and payload[0].get("cap_bnd") == "0000000000000000"
        and payload[0].get("no_new_privs") == "1",
        "payload_cannot_migrate": session["payload_cannot_join_epoch"] and session["payload_cannot_join_records"],
        "unlisted_client_refused": "error" in session["foreign_client"],
        "payload_limits_set": session["limits"] == {"pids.max": "32", "memory.max": str(128 << 20)},
        # The whole epoch's helpers together: sixteen records at the per-helper limits.
        "payload_umask_private": session["umask"].get("reply") == 0o077,
        # No core dump: soft and hard limit 0, so a crash leaves no image of the helper.
        "payload_dumps_no_core": bool(session["payload_core_limits"])
        and all(limit == ["0", "0"] for limit in session["payload_core_limits"]),
        # A helper's file and SysV segment exist, in its epoch's own namespaces, while it runs;
        # host leftovers of a payload ID are gone once a purge has run, before the ID is reused.
        "payload_leftovers_purged": session["leftovers_present"] and siblings["staged"]["present"]
        and not siblings["leftovers_after_start"],
        # The epoch's own mount and IPC namespaces: its /tmp is another filesystem, and the
        # helper's file and segment are not on the host for anyone to reach.
        "payload_roots_private": session["namespaces"] == {"mount": True, "ipc": True, "tmp_is_its_own": True,
                                                            "file_not_on_host": True, "segment_not_on_host": True},
        # An unremovable leftover (another ID wrote into it; deeper than the walk) is closed
        # off rather than tainting the slice: the guardian stops cleanly and the next
        # scenario's guardian starts on a clean purge.
        # What could not be removed where it was is moved into the root-only quarantine and
        # taken apart there: names free, nothing payload-owned left, memory released.
        "unremovable_leftovers_released": siblings["names_freed"] and siblings["payload_owned_left"] == []
        and bool(siblings["squats"]) and siblings["squatted_payload_files_left"] == []
        and siblings["static_tree_logged"] and siblings["loop_mounted"] and not siblings["churn_logged"]
        and siblings["core_pattern_warned"] == siblings["core_pattern_warning_expected"]
        and not siblings["revisit_logged"] and siblings["outside_mounted"] and siblings["outside_file_kept"]
        and siblings["cover_mounted"] and not siblings["covered_payload_left"] and siblings["host_mounts_kept"]
        and siblings["fuse_mounted"] and not siblings["fuse_covered_payload_left"]
        and siblings["bad_fuse_mounted"] and not siblings["bad_fuse_payload_left"]
        and siblings["queue_made"] and siblings["queue_left"] is False and not siblings["crash_report_left"]
        and siblings["foreign_queue_made"] and siblings["foreign_queue_kept"] is True
        and session["guardian_stop"][0] == 0 and siblings["guardian_stop"][0] == 0,
        # epoch-N itself is bounded before it is delegated: nothing beside `records` escapes.
        "epoch_bounded": session["epoch_bounds"] == {"cgroup.max.depth": "40", "cgroup.max.descendants": "4096",
                                                    "pids.max": str(32 * 16 + 256),
                                                    "memory.max": str(16 * (128 << 20) + (512 << 20))}
        and session["subtree_caps"] == {"pids.max": "4096", "memory.max": str(8 << 30)},
        "epoch_limits_set": session["epoch_limits"] == {"pids.max": str(32 * 16), "memory.max": str(16 * (128 << 20))},
        # The payload, its escaped descendant and the fork attempts share 32 pids.
        "fork_bounded": isinstance(session["spawn"].get("reply"), int) and 0 < session["spawn"]["reply"] < 32,
        "escaped_descendant_contained": session["escaped_in_payload_cgroup"],
        "retired_after_close": session["close"].get("retired") is True,
        "payload_and_descendant_gone": session["payload_gone_after_close"] and session["escaped_gone_after_close"],
        "clean_stop": session["guardian_stop"][0] == 0 and not session["epochs_after_stop"]
        and not session["endpoint_after_stop"],
        "siblings_independent": siblings["first_close"].get("retired") is True and siblings["first_escaped_gone"]
        and siblings["second_escaped_alive"] and siblings["second_after_sibling_close"].get("reply") == "pong"
        and siblings["second_close"].get("retired") is True and siblings["second_escaped_gone"]
        and siblings["guardian_stop"][0] == 0 and not siblings["epochs_after_stop"],
        "nested_child_under_parent": (nested["nest"].get("result") or {}).get("ping") == "pong"
        and child_inside_parent(nested),
        "nested_child_retired": (nested["close_child"].get("result") or {}).get("retired") is True
        and nested["child_escaped_gone"] and nested["close"].get("retired") is True,
        "nested_clean_stop": nested["guardian_stop"][0] == 0 and not nested["epochs_after_stop"],
        "revoke_racing_launch": len(race["race"].get("outcomes", [])) == 7
        and all(o.get("retired") is True for o in race["race"]["outcomes"])
        and not race["payloads_left"] and not race["containers_left"]
        and race["guardian_stop"][0] == 0 and not race["epochs_after_stop"],
        "orphans_survive_crash": crash["epoch_frozen"] and crash["epoch_thawed"] and crash["payload_alive_after_crash"]
        and crash["escaped_alive_after_crash"],
        "cold_recovery_reclaims": crash["payload_gone_after_recovery"] and crash["escaped_gone_after_recovery"]
        and crash["epochs_after_restart"] == ["epoch-0000000000000006"],
        # Started with SIGCHLD ignored, it reset it: its startup purges settled, no slice tainted.
        "recovered_stop": crash["guardian_stop"][0] == 0 and not crash["epochs_after_stop"]
        and "could not remove" not in crash["guardian_stop"][1],
        "idle_lease_renewed": renewal["ping_after_idle"].get("reply") == "pong"
        and renewal["close"].get("retired") is True and renewal["guardian_stop"][0] == 0,
        "epoch_rollover": len(rollover["sessions"]) == ROLLOVER_SESSIONS
        and all(s["retired"] for s in rollover["sessions"])
        and len({tuple(s["epochs"]) for s in rollover["sessions"]}) >= 2 and rollover["guardian_alive"]
        # Only the current service: every earlier one was reaped, none left as a zombie.
        and len(rollover["guardian_children"]) == 1
        and rollover["guardian_stop"][0] == 0 and not rollover["epochs_after_stop"],
        "service_crash_reclaimed": service_crash["old_epoch_gone"] and service_crash["payload_gone"]
        and service_crash["escaped_gone"] and service_crash["guardian_alive"]
        and service_crash["next_session"]["retired"] and service_crash["guardian_stop"][0] == 0
        and not service_crash["epochs_after_stop"],
        # Read from the running payload, not the manifest: its own group and nothing else.
        # The real worker: it answers through the service as its own range ID, under the
        # identity filter, with its parent-watch thread created despite clone3 being refused.
        # A long-lived helper no longer stops new helpers: its spent epoch retires beside the
        # next, which serves every later session, from the other half of the ID range.
        "long_lived_overlap": all(s["retired"] for s in held["sessions"]) and len(held["epochs_while_held"]) == 2
        and held["holder_ping"].get("reply") == "pong" and held["holder_close"].get("retired") is True
        and bool(held["holder_uids"]) and bool(held["successor_uids"])
        and {(int(u) - PAYLOAD_BASE) // EPOCH_IDS for u in held["holder_uids"]}
        != {(int(u) - PAYLOAD_BASE) // EPOCH_IDS for u in held["successor_uids"]}
        and held["first_reclaimed"] and len(held["guardian_children"]) == 1
        and held["guardian_stop"][0] == 0 and not held["epochs_after_stop"],
        # E3 started while E1 still retired around H1: it took the other half and left H1's
        # files alone; E3's own handover waited for E1 and then happened.
        "second_overlap_halves": slice_of(second["third"].get("uids")) is not None
        and slice_of(second["third"].get("uids")) != slice_of(second["h1_uids"]) and second["h1_files_kept"]
        and all(s["retired"] for s in second["fill_first"] + second["fill_second"] + second["fill_third"])
        and second["third"]["retired"],
        "second_overlap_pending_handover": len(second["epochs_pending"]) == 2 and second["h1_files_purged"]
        and second["fourth"]["retired"] and second["fourth"]["epochs"][-1] not in second["epochs_pending"]
        and slice_of(second["fourth"].get("uids")) not in (None, slice_of(second["third"].get("uids")))
        and second["h1_close"].get("retired") is True and second["h3_close"].get("retired") is True
        and len(second["guardian_children"]) == 1 and second["guardian_stop"][0] == 0
        and not second["epochs_after_stop"],
        # Four epochs at once at the default limit: three retiring around their helpers, one
        # serving, every slice in use.
        "four_epochs_at_once": len(triple["epochs_held"]) == 4
        and len({slice_of(triple["h1_uids"]), slice_of(triple["h2_uids"]), slice_of(triple["h3_uids"]),
                 slice_of(triple["fourth"].get("uids"))} - {None}) == 4
        and all(s["retired"] for s in triple["fill_first"] + triple["fill_second"] + triple["fill_third"])
        and triple["third"]["retired"] and triple["fourth"]["retired"]
        and all(p.get("reply") == "pong" for p in triple["pings"])
        and all(c.get("retired") is True for c in triple["closes"])
        and len(triple["guardian_children"]) == 1 and triple["guardian_stop"][0] == 0
        and not triple["epochs_after_stop"],
        # A remote helper negotiates through the service as its own payload ID, under the filter.
        "remote_helper_negotiates": remote["negotiate"].get("replies") == [{"protocol": 1},
                                                                           {"remote_effect_protocol": 1}]
        and bool(remote["inspection"]["payload"]) and in_payload_range(remote["inspection"]["payload"][0].get("uid"))
        and remote["inspection"]["payload"][0].get("seccomp") == "2"
        and remote["close"].get("retired") is True and remote["guardian_stop"][0] == 0,
        "nested_in_retiring_epoch": len(retiring_nested["epochs_before_nest"]) == 2
        and (retiring_nested["nest"].get("result") or {}).get("ping") == "pong"
        and slice_of([retiring_nested["child_uid"]] if retiring_nested["child_uid"] else []) == slice_of(
            retiring_nested["parent_uids"])
        and (retiring_nested["close_child"].get("result") or {}).get("retired") is True
        and retiring_nested["close"].get("retired") is True and retiring_nested["guardian_stop"][0] == 0,
        # A refused epoch creation neither ends the guardian nor spins it: under a quarter of a
        # second of CPU in three seconds, a fresh epoch once creation works, a prompt stop.
        "failed_start_retried_with_backoff": restart["alive_while_blocked"] and restart["old_epoch_gone"]
        and restart["epochs_while_blocked"] == [] and restart["cpu_ticks_while_blocked"] < 25
        and len(restart["epochs_after_unblock"]) == 1 and restart["next_session"]["retired"]
        and restart["guardian_stop"][0] == 0 and restart["stop_seconds"] < 5 and restart["epochs_after_stop"] == [],
        # Each fault path ends as designed: a failed listing and a directory met again run
        # the purge again, a mount placed mid-walk is laid bare, and the mount API refused
        # means no queues (ENODEV), a rerun (no /dev/mqueue) or a purge through /dev/mqueue.
        # A payload ID outside every epoch's own mount namespace reaches no service: the
        # connection is closed without a reply (or never accepted).
        "outside_epoch_refused": outside["outcome"] in ("reply:0", "closed:ConnectionResetError",
                                                         "closed:BrokenPipeError", "connect:PermissionError")
        and outside["guardian_stop"][0] == 0,
        "purge_fault_paths": faults["faults_exit"] == 0 and len(faults["faults"]) == 6
        and all(faults["faults"].values()),
        # The manifest refuses a root linking into a user's directory, a user's own directory
        # and a link loop, and accepts root's own: staged under /run, as root.
        "purge_roots_refused": faults["roots_exit"] == 0 and faults["roots"].get("root_cases") == 4,
        "taken_payload_range_refused": taken["refused"][0] != 0
        and "manifest is invalid" in taken["refused"][1] and not taken["epochs"],
        "native_worker_runs": (worker["bootstrap"].get("result") or {}).get("protocol") == 1
        and bool(worker["inspection"]["payload"]) and in_payload_range(worker["inspection"]["payload"][0].get("uid"))
        and worker["inspection"]["payload"][0].get("seccomp") == "2"
        and int(worker["inspection"]["payload"][0].get("threads") or 0) >= 2
        and worker["close"].get("retired") is True and worker["guardian_stop"][0] == 0,
        "delegated_subtree_refused": delegated["delegated_refused"][0] != 0
        and "prepare operation 14" in delegated["delegated_refused"][1] and delegated["trusted_started"]
        and delegated["guardian_stop"][0] == 0 and not delegated["epochs_after_stop"],
        # Read from the running payload: its own range ID as group, with the same offset as its
        # user ID, and nothing else.
        "payload_group_private": in_payload_range(payload[0].get("gid")) and payload[0].get("gid") == payload[0].get(
            "uid") and payload[0].get("groups") == [],
        # Two live helpers are two accounts: neither can ptrace or signal the other.
        "siblings_distinct_accounts": len(siblings["payload_uids"]) == 2
        and all(in_payload_range(uid) for uid in siblings["payload_uids"]),
        "service_identity_filter": service[0].get("seccomp") == "2" and payload[0].get("seccomp") == "2",
        # EPERM is 1, ENOSYS 38: no way back to root, another group or a user namespace.
        "identity_filter_refuses_root": session["seccomp_probe"] == {
            "installed": True, "setresuid_root": 1, "setresgid_root": 1, "setuid_root": 1, "setgroups_root": 1,
            "setgroups_empty": 0, "unshare_user": 1, "clone_user": 1, "clone3": 38, "keyring": 1,
            "payload_switch": 0,
            "payload_last": 0, "beyond_range": 1, "chmod_plain": 0, "fchmod_setuid": 1, "fchmodat_setgid": 1,
            "open_setuid": 1, "mknod_setuid": 1, "fchmodat2_setuid": 1, "tmpfile_setuid": 1, "openat2": 38,
            "io_uring": 38, "openat2_control": 0, "io_uring_control": 0, "ring_enter": 38, "ring_register": 38,
            "subvolume_control": 25, "subvolume": 1, "setflags": 1, "ordinary_ioctl": 0},
        "nothing_left": not result["cleanup"]["leftovers"] and not result["cleanup"]["subtree_exists"]
        and not os.path.exists(OUTER) and not os.path.exists(STATE2)
        and not result["cleanup"]["accounts_present"] and not result["cleanup"]["groups_present"]
        and not result["cleanup"]["client_in_socket_group"],
    }


main()
