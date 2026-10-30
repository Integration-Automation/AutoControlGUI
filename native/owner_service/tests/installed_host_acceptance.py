"""Install the owner service the way README.md's administrator steps say, check the installed
host, and remove it again. Disposable hosts only: it adds accounts, a cgroup subtree and
files under /usr/libexec, /etc, /var/lib and /run.

Usage: sudo python3 -I installed_host_acceptance.py <owner_service dir> <repository root> <client account>
Prints one JSON object; exits 0 only when every expectation held.

The installed build keeps the production gate closed, so a client's lease is refused: what
this checks is the installation (content, ownership, the listener, the guardian and its
epoch's private roots) and the host's requirements, not a helper run.
"""
import ctypes
import grp
import hashlib
import json
import os
import pwd
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time

SOURCE, REPOSITORY, CLIENT = sys.argv[1], sys.argv[2], sys.argv[3]
SERVICE, SOCKET_GROUP = "acownsvc", "acownsock"
PAYLOAD_BASE, PAYLOAD_IDS = 50000, 128
LIBEXEC, ETC = "/usr/libexec/je_auto_control", "/etc/je_auto_control"
STATE_PARENT, STATE = "/var/lib/je_auto_control", "/var/lib/je_auto_control/owner"
RUN, ENDPOINT = "/run/je_auto_control", "/run/je_auto_control/owner.sock"
SUBTREE = "/sys/fs/cgroup/je_auto_control.owner"
BINDING = {"endpoint": ENDPOINT,
           "policies": [{"argv": ["/usr/bin/python3", "-I", "-u", "-m",
                                  "je_auto_control.utils.agent_runtime.native_worker"], "policy": 1}]}
report = {"evidence": "installed-host acceptance in one WSL distro", "steps": {}}
undo = []


def run(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, text=True, timeout=600, **kwargs)


def must(argv, **kwargs):
    result = run(argv, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{argv[0]}: {result.stderr.strip()}")
    return result


def _taken(identifier):
    try:
        pwd.getpwuid(identifier)
        return True
    except KeyError:
        pass
    try:
        grp.getgrgid(identifier)
        return True
    except KeyError:
        return False


def provision():
    """README steps 1 and 4: accounts, the socket group, the directories and the subtree."""
    if any(_taken(i) for i in range(PAYLOAD_BASE, PAYLOAD_BASE + PAYLOAD_IDS)):
        raise RuntimeError("payload range already in use")
    for path in (LIBEXEC, ETC, STATE_PARENT, RUN, SUBTREE):
        if os.path.lexists(path):
            raise RuntimeError(f"{path} exists: not a fresh host")
    must(["groupadd", "--system", SOCKET_GROUP])
    undo.append(["groupdel", SOCKET_GROUP])
    must(["useradd", "--system", "--no-create-home", "--shell", "/usr/sbin/nologin", "--user-group", SERVICE])
    undo.append(["userdel", SERVICE])
    must(["usermod", "--append", "--groups", SOCKET_GROUP, CLIENT])
    undo.append(["gpasswd", "--delete", CLIENT, SOCKET_GROUP])
    with open("/sys/fs/cgroup/cgroup.subtree_control") as handle:
        report["steps"]["root_controllers"] = handle.read().split()
    for path, mode in ((STATE_PARENT, 0o755), (STATE, 0o700), (RUN, 0o755), (SUBTREE, 0o755)):
        os.mkdir(path)
        if not path.startswith("/sys/"):
            os.chmod(path, mode)


def client_namespaces():
    """`stat -L -c '%d %i'` of the client's user, pid, mnt and cgroup namespaces."""
    out = must(["runuser", "-u", CLIENT, "--", "stat", "-L", "-c", "%d %i", "/proc/self/ns/user",
                "/proc/self/ns/pid", "/proc/self/ns/mnt", "/proc/self/ns/cgroup"]).stdout.split()
    device = out[0]
    return device, out[1], out[3], out[5], out[7]


def manifest(path):
    """README step 2: the example manifest with every EDIT value filled in."""
    with open(os.path.join(SOURCE, "config/owner_manifest.example.c")) as handle:
        text = handle.read()
    service, client = pwd.getpwnam(SERVICE), pwd.getpwnam(CLIENT)
    device, user, pid, mount, cgroup = client_namespaces()
    values = {"SERVICE_UID": f"{service.pw_uid}u", "SERVICE_GID": f"{service.pw_gid}u",
              "PAYLOAD_UID": f"{PAYLOAD_BASE}u", "PAYLOAD_GID": f"{PAYLOAD_BASE}u",
              "SOCKET_GID": f"{grp.getgrnam(SOCKET_GROUP).gr_gid}u",
              "CLIENT_UID": f"{client.pw_uid}u", "CLIENT_GID": f"{client.pw_gid}u",
              "NS_DEVICE": f"{device}ULL", "NS_USER": f"{user}ULL", "NS_PID": f"{pid}ULL",
              "NS_MOUNT": f"{mount}ULL", "NS_CGROUP": f"{cgroup}ULL"}
    for name, value in values.items():
        text, count = re.subn(rf"^#define {name} \S+$", f"#define {name} {value}", text, flags=re.M)
        if count != 1:
            raise RuntimeError(f"manifest: {name} not found once")
    installation = ", ".join(str(b) for b in secrets.token_bytes(16))
    text, count = re.subn(r"\.installation = \{0\},", f".installation = {{{installation}}},", text)
    if count != 1:
        raise RuntimeError("manifest: installation not found once")
    with open(path, "w") as handle:
        handle.write(text)
    report["steps"]["manifest_values"] = values


def _digest(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def _owned_by_root_unwritable(path):
    status = os.lstat(path)
    return status.st_uid == 0 and status.st_gid == 0 and not status.st_mode & 0o022


def install(build):
    """README steps 3 and 6; then compare what is installed against what was built."""
    os.mkdir(LIBEXEC, 0o755)
    os.mkdir(ETC, 0o755)
    for name in ("owner_guardian", "owner_service"):
        must(["install", "-o", "root", "-g", "root", "-m", "0755", os.path.join(build, name),
              os.path.join(LIBEXEC, name)])
    binding = os.path.join(ETC, "owner_service.json")
    with open(binding, "w") as handle:
        json.dump(BINDING, handle)
    os.chmod(binding, 0o644)
    ancestors = []
    path = LIBEXEC
    while path != "/":
        ancestors.append(path)
        path = os.path.dirname(path)
    report["steps"]["installed"] = {
        "same_content": {name: _digest(os.path.join(build, name)) == _digest(os.path.join(LIBEXEC, name))
                         for name in ("owner_guardian", "owner_service")},
        "only_expected_files": sorted(os.listdir(LIBEXEC)) == ["owner_guardian", "owner_service"],
        "binaries_root_unwritable": all(_owned_by_root_unwritable(os.path.join(LIBEXEC, n))
                                        and not os.lstat(os.path.join(LIBEXEC, n)).st_mode & 0o7000
                                        for n in ("owner_guardian", "owner_service")),
        "ancestors_root_unwritable": all(_owned_by_root_unwritable(p) for p in ancestors),
        "binding_matches": json.load(open(binding)) == BINDING and _owned_by_root_unwritable(binding),
        "state_root_only": stat.S_IMODE(os.lstat(STATE).st_mode) == 0o700 and os.lstat(STATE).st_uid == 0,
    }


def _mount_api_mqueue():
    """fsopen("mqueue") as root: the purge's detached queue mount is possible here."""
    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.syscall(430, b"mqueue", 1)  # SYS_fsopen, FSOPEN_CLOEXEC
    if fd < 0:
        return f"errno {ctypes.get_errno()}"
    os.close(fd)
    return "ok"


def host_requirements():
    """The README's host requirements, as this host meets them."""
    with open("/proc/sys/kernel/core_pattern") as handle:
        core_pattern = handle.read().strip()
    journald = os.path.exists("/run/systemd/journal/socket")
    found = run(["find", "/", "-xdev", "-type", "d", "-perm", "-0002", "-not", "-path", "/proc/*"]).stdout
    writable = sorted(p for p in found.split("\n") if p)
    mounts = {}
    with open("/proc/self/mountinfo") as handle:
        for line in handle:
            fields = line.split()
            mounts[fields[4]] = fields[fields.index("-") + 1]
    mount_api = _mount_api_mqueue()
    outside = [p for p in writable if _reachable(p) and not any(p == r or p.startswith(r + "/") for r in PRIVATE)]
    report["steps"]["host"] = {"core_pattern": core_pattern, "journald_running": journald,
                               "mount_api_mqueue": mount_api, "dev_mqueue": mounts.get("/dev/mqueue"),
                               "world_writable": writable,
                               "kernel": os.uname().release, "machine": os.uname().machine}
    # README's host requirements, as this host meets them. A host that misses one is reported,
    # not failed: the installation is checked either way, and the gate stays closed.
    report["steps"]["host_requirements"] = {
        "journal_not_kept": not journald,
        "core_pattern_file_or_known": not core_pattern.startswith("|") or os.path.basename(
            core_pattern[1:].split()[0]) in ("systemd-coredump", "apport"),
        "mount_api_or_mqueue": mount_api == "ok" or mounts.get("/dev/mqueue") == "mqueue",
        # World-writable directories a helper can reach that no private root covers.
        "writable_outside_roots": outside,
    }


PRIVATE = ("/tmp", "/var/tmp", "/dev/shm", "/run/lock", "/var/crash")


def _reachable(path):
    """True when anyone can search every directory down to `path` and write into it."""
    while True:
        try:
            if not os.stat(path).st_mode & 0o001:
                return False
        except OSError:
            return False
        if path == "/":
            return True
        path = os.path.dirname(path)


def _drain(stream, sink):
    for line in stream:
        sink.append(line)


def start_guardian():
    """README step 5, without a supervisor (this host runs none): the guardian as root."""
    guardian = subprocess.Popen([os.path.join(LIBEXEC, "owner_guardian")], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, env={})
    guardian.log = []
    threading.Thread(target=_drain, args=(guardian.stderr, guardian.log), daemon=True).start()
    limit = time.monotonic() + 30
    while not os.path.exists(ENDPOINT) and time.monotonic() < limit:
        if guardian.poll() is not None:
            raise RuntimeError(f"guardian exited {guardian.returncode}: {''.join(guardian.log)}")
        time.sleep(0.1)
    time.sleep(0.5)
    return guardian


def _service_pid(guardian):
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/status") as handle:
                status = dict(line.split(":", 1) for line in handle if ":" in line)
        except OSError:
            continue
        if status.get("PPid", "").strip() == str(guardian.pid) and \
                status.get("Uid", "").split()[0] == str(pwd.getpwnam(SERVICE).pw_uid):
            return int(entry)
    return 0


def running_checks(guardian):
    service = _service_pid(guardian)
    listener = os.lstat(ENDPOINT)
    private = {}
    if service:
        with open(f"/proc/{service}/mountinfo") as handle:
            epoch_mounts = sorted(line.split()[4] for line in handle if " autocontrol-epoch " in line)
        private = {"mount": os.readlink(f"/proc/{service}/ns/mnt") != os.readlink("/proc/self/ns/mnt"),
                   "ipc": os.readlink(f"/proc/{service}/ns/ipc") != os.readlink("/proc/self/ns/ipc"),
                   "epoch_tmpfs": epoch_mounts}
    report["steps"]["running"] = {
        "listener_socket": stat.S_ISSOCK(listener.st_mode), "listener_uid": listener.st_uid,
        "listener_group": grp.getgrgid(listener.st_gid).gr_name,
        "listener_mode": oct(stat.S_IMODE(listener.st_mode)),
        "epochs": sorted(n for n in os.listdir(SUBTREE) if n.startswith("epoch-")),
        "service_pid": service, "service_private": private,
        "client": _as_client(CLIENT), "stranger": _as_client("nobody"),
    }


_CLIENT = """
import json, os, sys
sys.path.insert(0, sys.argv[2])
from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.helper_owner_linux import OwnerServiceChannel, SeqpacketTransport
try:
    channel = OwnerServiceChannel(SeqpacketTransport(sys.argv[1]), 1)
    print(json.dumps(["value", channel.request("ping", {}, timeout=10)]))
except (AgentTaskError, OSError) as error:
    print(json.dumps(["error", type(error).__name__, str(error)]))
"""


def _as_client(account):
    """The package's client, run as `account`: what a lease request meets on this host."""
    result = run(["runuser", "-u", account, "--", "/usr/bin/python3", "-I", "-c", _CLIENT, ENDPOINT, REPOSITORY])
    try:
        return json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return ["unreadable", result.returncode, result.stderr[-400:]]


def stop(guardian):
    guardian.send_signal(signal.SIGTERM)
    try:
        guardian.wait(timeout=60)
    except subprocess.TimeoutExpired:
        guardian.kill()
        guardian.wait()
    time.sleep(0.2)
    log = "".join(guardian.log)
    report["steps"]["stop"] = {"exit": guardian.returncode, "log": log[-8000:],
                               "epochs_after": sorted(n for n in os.listdir(SUBTREE) if n.startswith("epoch-")),
                               "endpoint_after": os.path.exists(ENDPOINT)}


def uninstall():
    leftovers = {}
    for path in (LIBEXEC, ETC, STATE_PARENT, RUN):
        shutil.rmtree(path, ignore_errors=True)
    if os.path.isdir(SUBTREE):
        for directory, _subdirs, _files in sorted(os.walk(SUBTREE), key=lambda e: -len(e[0])):
            try:
                os.rmdir(directory)
            except OSError as error:
                leftovers[directory] = str(error)
    for argv in reversed(undo):
        result = run(argv)
        if result.returncode:
            leftovers[argv[-1]] = result.stderr.strip()
    report["uninstalled"] = {"leftovers": leftovers,
                             "paths_left": [p for p in (LIBEXEC, ETC, STATE_PARENT, RUN, SUBTREE)
                                            if os.path.lexists(p)]}


def main():
    guardian = None
    try:
        provision()
        work = tempfile.mkdtemp(prefix="autocontrol-installed-")
        manifest(os.path.join(work, "owner_manifest.c"))
        build = os.path.join(work, "build")
        report["steps"]["build"] = must(["sh", os.path.join(SOURCE, "build.sh"),
                                         os.path.join(work, "owner_manifest.c"), build]).stdout.strip()
        install(build)
        shutil.rmtree(work, ignore_errors=True)
        host_requirements()
        guardian = start_guardian()
        running_checks(guardian)
        stop(guardian)
        guardian = None
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if guardian is not None and guardian.poll() is None:
            guardian.kill()
            guardian.wait()
        uninstall()
    steps = report["steps"]
    installed, running, stopped = steps.get("installed", {}), steps.get("running", {}), steps.get("stop", {})
    host = steps.get("host", {})
    private = running.get("service_private", {})
    report["expectations"] = {
        "installed_content_matches_build": bool(installed) and all(installed["same_content"].values())
        and installed["only_expected_files"] and installed["binding_matches"],
        "installed_root_owned": bool(installed) and installed["binaries_root_unwritable"]
        and installed["ancestors_root_unwritable"] and installed["state_root_only"],
        "listener_published": running.get("listener_socket") is True and running.get("listener_uid") == 0
        and running.get("listener_group") == SOCKET_GROUP,
        "epoch_running": len(running.get("epochs", [])) == 1 and bool(running.get("service_pid")),
        "epoch_roots_private": private.get("mount") is True and private.get("ipc") is True
        and {"/tmp", "/var/tmp", "/dev/shm"} <= set(private.get("epoch_tmpfs", [])),
        # The installed build keeps the gate closed: the client's lease is refused, not served.
        "installed_gate_closed": running.get("client", [None])[0] == "error",
        "stranger_refused": running.get("stranger", [None])[0] == "error",
        "core_pattern_warned": ("core_pattern" in stopped.get("log", "")) == host.get("core_pattern", "").startswith(
            "|"),
        "clean_stop": stopped.get("exit") == 0 and stopped.get("epochs_after") == []
        and stopped.get("endpoint_after") is False,
        "uninstalled": report.get("uninstalled", {}) == {"leftovers": {}, "paths_left": []},
        "completed": "error" not in report,
    }
    print(json.dumps(report, indent=1))
    return 0 if all(report["expectations"].values()) else 1


if __name__ == "__main__":
    if os.geteuid() != 0:
        print(json.dumps({"error": "run as root on a disposable host"}))
        sys.exit(77)
    sys.exit(main())
