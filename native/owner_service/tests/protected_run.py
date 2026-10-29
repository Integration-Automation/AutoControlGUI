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
import time

SOURCE, REPOSITORY = sys.argv[1], sys.argv[2]
SRC, TESTS = os.path.join(SOURCE, "src"), os.path.join(SOURCE, "tests")
CC = os.environ.get("CC", "cc")
OPT, STATE, RUN = "/opt/autocontrol-test", "/var/lib/autocontrol-test", "/run/autocontrol-test"
SUBTREE = "/sys/fs/cgroup/autocontrol-test"
ENDPOINT = RUN + "/owner.sock"
CLIENT = "user"
ACCOUNTS = ("acsvc", "acpay", "acother")
SOCKET_GROUP = "acsock"
ROLLOVER_SESSIONS = 10  # More than the manifest's quota of 8 leases per epoch.
SERVICE_SOURCES = ["native_owner.c", "native_owner_lease.c", "native_launch_linux.c", "native_relay_linux.c",
                   "service_peer_linux.c"]
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
    for name in ACCOUNTS:
        try:
            pwd.getpwnam(name)
        except KeyError:
            # Every account has its own primary group. acother joins the socket group, so it
            # reaches the socket and only the guardian's principal check can refuse it. acpay
            # never does: the service hands the socket group to nested-capable payloads only.
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
    service, payload = pwd.getpwnam("acsvc"), pwd.getpwnam("acpay")
    client = pwd.getpwnam(CLIENT)
    values = {"SERVICE_UID": service.pw_uid, "SERVICE_GID": service.pw_gid, "PAYLOAD_UID": payload.pw_uid,
              "PAYLOAD_GID": payload.pw_gid, "CLIENT_UID": client.pw_uid, "CLIENT_GID": client.pw_gid,
              "SOCKET_GID": grp.getgrnam(SOCKET_GROUP).gr_gid,
              **namespaces()}
    defines = [f"-D{key}={value}u" if not key.startswith("NS_") else f"-D{key}={value}ULL"
               for key, value in values.items()]
    defines.append(f'-DPAYLOAD_EXECUTABLE="{OPT}/owner_core_acceptance"')
    defines += [f'-DNESTED_PARENT="{OPT}/nested_parent.py"', f'-DREPOSITORY="{REPOSITORY}"',
                f'-DENDPOINT="{ENDPOINT}"']
    shutil.copy(os.path.join(TESTS, "nested_parent.py"), OPT + "/nested_parent.py")
    os.chmod(OPT + "/nested_parent.py", 0o644)
    gcc(SERVICE_SOURCES + ["native_service.c", "service_bootstrap_linux.c", "service_main.c", "protected_manifests.c"],
        OPT + "/service_main", defines + ["-DNO_PROTECTED_ACCEPTANCE"])
    gcc(SERVICE_SOURCES + ["guardian_main.c", "guardian_epoch_linux.c", "guardian_journal.c",
                           "guardian_forward_linux.c", "protected_manifests.c"], OPT + "/guardian", defines)
    gcc(["native_owner.c", "native_owner_lease.c", "native_launch_linux.c", "native_relay_linux.c",
         "owner_core_acceptance.c"], OPT + "/owner_core_acceptance", acceptance=True)
    report["accounts"] = {k: v for k, v in values.items() if not k.startswith("NS_")}


def start_guardian():
    guardian = subprocess.Popen([OPT + "/guardian"], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env={})
    limit = time.monotonic() + 15
    while not os.path.exists(ENDPOINT) and time.monotonic() < limit:
        if guardian.poll() is not None:
            raise RuntimeError(f"guardian exited {guardian.returncode}: {guardian.stderr.read()}")
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
    return guardian.returncode, guardian.stderr.read()[-2000:]


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
            "no_new_privs": fields.get("NoNewPrivs")}


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def migration_denied(target_dir):
    result = run(["runuser", "-u", "acpay", "--", "/bin/sh", "-c", f"echo $$ > {target_dir}/cgroup.procs"])
    return result.returncode != 0 and "Permission denied" in result.stderr


def escaped_in_payload(pid, epoch):
    if not isinstance(pid, int) or pid <= 0 or not pid_alive(pid):
        return False
    with open(f"/proc/{pid}/cgroup") as handle:
        path = handle.read().strip().partition("::")[2]
    return path.startswith(f"/autocontrol-test/{epoch}/records/") and path.endswith("/payload")


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
    steps["payload_cannot_join_epoch"] = migration_denied(f"{SUBTREE}/{epoch}")
    steps["payload_cannot_join_records"] = migration_denied(f"{SUBTREE}/{epoch}/records")
    foreign = client("foreign", account="acother")
    steps["foreign_client"] = read_json(foreign)
    foreign.wait(timeout=30)
    container = os.path.dirname(SUBTREE + steps["inspection"]["payload_cgroups"][0])
    steps["limits"] = {name: open(os.path.join(container, name)).read().strip()
                       for name in ("pids.max", "memory.max")}
    holder.stdin.write("spawn\n")
    holder.stdin.flush()
    steps["spawn"] = read_json(holder)
    pids = steps["inspection"]["payload_pids"]
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


def scenario_siblings(steps):
    """Two clients, two leases, two payloads: closing one leaves the other serving."""
    guardian = start_guardian()
    first, second = client("hold"), client("hold")
    steps["first"], steps["second"] = read_json(first), read_json(second)
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
            holder.stdin.write("close\n")
            holder.stdin.flush()
            closed = read_json(holder)
            holder.wait(timeout=30)
            return {"attempts": attempt, "epochs": epoch, "retired": closed.get("retired") is True}
        holder.kill()
        holder.wait()
        time.sleep(0.25)
    return {"attempts": 40, "retired": False}


def scenario_rollover(steps):
    """Spending the quota drains the epoch; the same guardian grants the next one."""
    guardian = start_guardian()
    steps["sessions"] = [rollover_session() for _ in range(ROLLOVER_SESSIONS)]
    steps["guardian_alive"] = guardian.poll() is None
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


def scenario_cold_recovery(steps):
    guardian = start_guardian()
    epoch = epochs()[-1]
    holder = client("hold")
    steps["request"] = read_json(holder)
    inspection = session_inspection(epoch)
    steps["payload_pids"] = inspection["payload_pids"]
    escaped = steps["request"].get("escaped")
    steps["escaped_in_payload_cgroup"] = escaped_in_payload(escaped, epoch)
    os.kill(guardian.pid, signal.SIGKILL)
    guardian.wait()
    for directory, pid in procs_under(f"{SUBTREE}/{epoch}"):
        if os.path.basename(directory).startswith("service-"):
            os.kill(pid, signal.SIGKILL)
    time.sleep(0.5)
    steps["payload_alive_after_crash"] = any(pid_alive(p) for p in inspection["payload_pids"])
    steps["escaped_alive_after_crash"] = isinstance(escaped, int) and pid_alive(escaped)
    steps["epochs_after_crash"] = epochs()
    holder.stdin.close()
    holder.kill()
    holder.wait()
    if os.path.exists(ENDPOINT):
        os.unlink(ENDPOINT)  # A crashed guardian leaves its socket; the next one replaces only a socket.
    restarted = start_guardian()
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
    for path in (STATE, RUN, OPT):
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
        scenario_siblings(report["steps"]["siblings"])
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
    except Exception as error:  # reason: cleanup must run and the failure must be reported, not lost
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        cleanup()
    report["expectations"] = expectations(report)
    print(json.dumps(report))
    raise SystemExit(0 if report["expectations"] and all(report["expectations"].values()) else 1)


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
    inspection = session.get("inspection", {})
    service, payload = inspection.get("service", [{}]), inspection.get("payload", [{}])
    if "error" in result or not all((session, crash, siblings, nested, race, renewal, rollover, service_crash)):
        return {"completed": False}
    return {
        "protected_reply": session["request"].get("reply") == "pong",
        # Exactly CAP_SETUID, CAP_SETGID and CAP_SETPCAP, as the service account.
        "service_account_and_capabilities": service[0].get("uid") == str(result["accounts"]["SERVICE_UID"])
        and service[0].get("cap_eff") == "00000000000001c0",
        # A code-execution bug in the service cannot regain more than those three.
        "service_bounding_set_and_no_new_privs": service[0].get("cap_bnd") == "00000000000001c0"
        and service[0].get("no_new_privs") == "1",
        "payload_account_without_capabilities": payload[0].get("uid") == str(result["accounts"]["PAYLOAD_UID"])
        and payload[0].get("cap_eff") == "0000000000000000" and payload[0].get("cap_bnd") == "0000000000000000"
        and payload[0].get("no_new_privs") == "1",
        "payload_cannot_migrate": session["payload_cannot_join_epoch"] and session["payload_cannot_join_records"],
        "unlisted_client_refused": "error" in session["foreign_client"],
        "payload_limits_set": session["limits"] == {"pids.max": "32", "memory.max": str(128 << 20)},
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
        "orphans_survive_crash": crash["payload_alive_after_crash"] and crash["escaped_alive_after_crash"],
        "cold_recovery_reclaims": crash["payload_gone_after_recovery"] and crash["escaped_gone_after_recovery"]
        and crash["epochs_after_restart"] == ["epoch-0000000000000006"],
        "recovered_stop": crash["guardian_stop"][0] == 0 and not crash["epochs_after_stop"],
        "idle_lease_renewed": renewal["ping_after_idle"].get("reply") == "pong"
        and renewal["close"].get("retired") is True and renewal["guardian_stop"][0] == 0,
        "epoch_rollover": len(rollover["sessions"]) == ROLLOVER_SESSIONS
        and all(s["retired"] for s in rollover["sessions"])
        and len({tuple(s["epochs"]) for s in rollover["sessions"]}) >= 2 and rollover["guardian_alive"]
        and rollover["guardian_stop"][0] == 0 and not rollover["epochs_after_stop"],
        "service_crash_reclaimed": service_crash["old_epoch_gone"] and service_crash["payload_gone"]
        and service_crash["escaped_gone"] and service_crash["guardian_alive"]
        and service_crash["next_session"]["retired"] and service_crash["guardian_stop"][0] == 0
        and not service_crash["epochs_after_stop"],
        "payload_group_private": result["accounts"]["PAYLOAD_GID"] not in (
            result["accounts"]["CLIENT_GID"], result["accounts"]["SOCKET_GID"]),
        "nothing_left": not result["cleanup"]["leftovers"] and not result["cleanup"]["subtree_exists"]
        and not result["cleanup"]["accounts_present"] and not result["cleanup"]["groups_present"]
        and not result["cleanup"]["client_in_socket_group"],
    }


main()
