"""Host objects the protected acceptance makes and inspects: FUSE covers, POSIX queues, SysV
segments, staged trees, and an epoch's view of its own namespaces. Imported by
protected_run.py; nothing here provisions or removes the harness's own fixtures."""
import ctypes
import errno
import json
import os
import pwd
import struct
import subprocess
import tempfile
import threading


def dead_fuse_mount(path, owner):
    """A FUSE mount at `path` belonging to `owner`, without allow_other, whose daemon is gone:
    root is refused a getattr on it, as on any user's sshfs or AppImage mount."""
    libc = ctypes.CDLL(None, use_errno=True)
    device = os.open("/dev/fuse", os.O_RDWR)
    options = f"fd={device},rootmode=40000,user_id={owner},group_id={owner}".encode()
    mounted = libc.mount(b"cover", path.encode(), b"fuse", 0, options) == 0
    os.close(device)  # The daemon is gone; the mount stays, dead.
    return mounted


def bad_fuse_mount(path, owner):
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


def payload_queue(uid, name=QUEUE_NAME):
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


def queue_exists(name=QUEUE_NAME):
    """True when the queue is there (it is then removed); None when that cannot be told."""
    libc = ctypes.CDLL(None, use_errno=True)
    queue = libc.mq_open(name, os.O_RDONLY)
    if queue >= 0:
        libc.mq_close(queue)
        libc.mq_unlink(name)
        return True
    return False if ctypes.get_errno() == errno.ENOENT else None


def in_payload(pid, path):
    """`path` as the payload process `pid` sees it: through its root, in its mount namespace."""
    return f"/proc/{pid}/root{path}"


def shm_in_payload(pid, shmid):
    """True when `shmid` is a segment in the IPC namespace of process `pid`."""
    listing = subprocess.run(["nsenter", "-t", str(pid), "-i", "cat", "/proc/sysvipc/shm"], capture_output=True,
                             text=True, timeout=30).stdout
    return any(line.split()[1] == str(shmid) for line in listing.splitlines()[1:] if line.split())


def namespaces_private(pid, left, ids):
    """The epoch's own mount and IPC namespaces: its /tmp is another filesystem, and what the
    helper left there, file and SysV segment, is not on the host. `ids`: the payload range."""
    def namespace(of, kind):
        return os.readlink(f"/proc/{of}/ns/{kind}")
    try:
        return {"mount": namespace(pid, "mnt") != namespace("self", "mnt"),
                "ipc": namespace(pid, "ipc") != namespace("self", "ipc"),
                "tmp_is_its_own": os.stat(in_payload(pid, "/tmp")).st_dev != os.stat("/tmp").st_dev,
                "file_not_on_host": os.path.exists(in_payload(pid, left[0])) and not os.path.exists(left[0]),
                "segment_not_on_host": shm_in_payload(pid, left[1]) and not host_payload_segment(left[1], ids)}
    except OSError as error:
        return {"error": str(error)}


def payload_segment(uid):
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


def staged_chain(top_dir, levels, uid):
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


def shm_exists(shmid):
    """True when `shmid` is a segment in this process's IPC namespace."""
    with open("/proc/sysvipc/shm") as handle:
        return any(line.split()[1] == str(shmid) for line in handle.readlines()[1:])


def host_payload_segment(shmid, ids):
    """True when this IPC namespace has segment `shmid` and an ID of the range `ids` owns it:
    another namespace's segment may carry the same number."""
    with open("/proc/sysvipc/shm") as handle:
        rows = [line.split() for line in handle.readlines()[1:]]
    return any(row[1] == str(shmid) and int(row[7]) in ids for row in rows if len(row) > 7)


def marker_holders(path):
    """Processes that still see `path` through their own root. Written with a random name into
    one epoch's private tmpfs, it tells that tmpfs from any later one: device numbers and
    namespace inodes are reused once freed, a random name is not."""
    holders = []
    for entry in os.listdir("/proc"):
        if entry.isdigit() and os.path.lexists(f"/proc/{entry}/root{path}"):
            holders.append(int(entry))
    return holders


# A nested open a service answers: run as a payload ID, it asks for a child lease of a record
# that does not exist. Prints the class and message of what the client met.
NESTED_PROBE = """
import json, sys
sys.path.insert(0, sys.argv[2])
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.helper_owner_linux import OwnerServiceChannel, SeqpacketTransport
from je_auto_control.utils.agent_runtime.owner_service_nested import NestedGrant
channel = OwnerServiceChannel(SeqpacketTransport(sys.argv[1]), 2, parent=NestedGrant(((142, 1), (0, 1)), bytes(32)))
try:
    print(json.dumps(["value", channel.request("ping", {}, timeout=10)]))
except AgentTaskError as error:
    print(json.dumps([type(error).__name__, str(error)]))
"""


def probe_as(uid, prefix, endpoint, repository):
    """NESTED_PROBE as payload ID `uid`, started through `prefix` (nsenter into a namespace,
    or nothing for the host's); the client's outcome as [class, message]."""
    def drop():
        os.setgroups([])
        os.setresgid(uid, uid, uid)
        os.setresuid(uid, uid, uid)
    try:
        probe = subprocess.run([*prefix, "/usr/bin/python3", "-I", "-c", NESTED_PROBE, endpoint, repository],
                               preexec_fn=None if prefix else drop, capture_output=True, text=True, timeout=60)
    except subprocess.SubprocessError as error:  # A timeout or a failed drop fails the expectation.
        return [type(error).__name__, str(error)]
    try:
        return json.loads(probe.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return ["unreadable", probe.returncode, probe.stderr[-400:]]
