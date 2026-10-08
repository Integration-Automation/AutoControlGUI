"""Keep scripts and settings in step across machines, offline included.

Each user has one bucket on a sync server; every machine merges its changes
into it. One call does a whole cycle -- stage local changes, push what is
queued, merge what came back, apply it locally::

    report = ac.config_sync_run(
        "http://127.0.0.1:8765", "alice",
        scripts_dir="~/automation/scripts")       # + hotkeys, triggers, address book
    print(report["state"], report["revision"], report["pending"], report["conflicts"])

The server is the signaling server; it keeps buckets in SQLite, so they
survive a restart::

    python -m je_auto_control.utils.remote_desktop.signaling_server \\
        --bind 127.0.0.1 --port 8765 --shared-secret "$AC_SIGNALING_SECRET" \\
        --config-db /var/lib/autocontrol/config_sync.sqlite3     # or AC_SIGNALING_CONFIG_DB

What ``state`` means:

``synced``           nothing is waiting
``pending``          changes are queued and will be sent on the next run
``offline``          the server was not reached, or an earlier failure is still backing
                     off (``error`` says which); nothing was lost, the queue is on disk
``conflict``         two machines changed one entry apart -- both versions are kept
``resync_required``  this device was retired; call ``ac.config_sync_full_resync``

Things that are deliberate:

* **No clock decides a merge.** Each entry carries a version vector; a change
  made knowing the other wins, two changes made apart are both kept until a
  person chooses with ``ac.config_sync_resolve(server, user, section, key, choice)``.
* **A write names the revision it was built on** (wire version 2). The server
  refuses it with HTTP 409 when another machine got there first and the client
  merges and retries; a bare bucket from an older client is answered 428.
* **Secrets and machine paths do not travel.** A script holding a literal
  secret is withheld (use ``${secrets.NAME}``); applying synced data never
  enables a hotkey or a trigger.

The same cycle is ``AC_config_sync_run`` / ``_status`` / ``_resolve`` /
``_full_resync`` in an action file, four MCP tools, and the Config Sync tab.

``--validate`` plays two machines against a store in a temp directory. Its
server is a few lines of ``http.server`` on 127.0.0.1 speaking the same wire
format over the real ``ConfigStore`` -- a stand-in for the signaling server so
the example needs no extra. Only script files in temp folders are synced; this
machine's hotkeys, triggers and address book are not read. Without the flag
the script prints the recorded status for ``--server`` / ``--user`` (no
network) and syncs only with ``--run``.
"""
import argparse
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

import je_auto_control as ac

_USER = "alice"


def _handler(store_path: Path) -> type:
    """A request handler serving ``GET`` / ``PUT /config/<user>`` from ``store_path``."""

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: Dict[str, Any]) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _user(self) -> str:
            return unquote(self.path.rsplit("/", 1)[-1])

        def do_GET(self) -> None:  # noqa: N802  # reason: http.server's naming
            bucket = ac.ConfigStore(store_path).get(self._user())
            if bucket is None:
                self._send(404, {"detail": "no bucket"})
            else:
                self._send(200, {**bucket.to_dict(), "version": 2})

        def do_PUT(self) -> None:  # noqa: N802  # reason: http.server's naming
            envelope = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if envelope.get("version") != 2:
                self._send(428, {"detail": "a version-2 write is required"})
                return
            try:
                revision = ac.ConfigStore(store_path).commit(
                    self._user(), ac.ConfigBucket.from_dict(envelope["bucket"]),
                    base_revision=envelope["base_revision"],
                    operation_id=envelope["operation_id"])
            except ac.RevisionConflictError as conflict:
                self._send(409, {"detail": "revision conflict",
                                 "revision": conflict.current_revision})
                return
            self._send(200, {"ok": True, "revision": revision, "version": 2})

        def log_message(self, *_args: Any) -> None:
            """Keep the example's output to what it prints itself."""

    return Handler


class LoopbackServer:
    """The stand-in sync server: start, stop, start again on the same store."""

    def __init__(self, store_path: Path) -> None:
        self._store_path = store_path
        self._server: Optional[ThreadingHTTPServer] = None
        self.port = 0

    @property
    def url(self) -> str:
        """Where clients reach it."""
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> None:
        """Listen on 127.0.0.1 (the same port again after a stop)."""
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), _handler(self._store_path))
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        """Stop listening; the store file stays."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None


class Machine:
    """One computer: its own scripts folder, outbox file and device id."""

    def __init__(self, name: str, root: Path, server: LoopbackServer) -> None:
        self.name = name
        self.scripts = root / name / "scripts"
        self.scripts.mkdir(parents=True)
        self._outbox = root / name / "outbox.sqlite3"
        self._server = server

    def _options(self) -> Dict[str, Any]:
        return {"device_id": self.name, "sections": "scripts", "timeout_s": 2.0,
                "scripts_dir": str(self.scripts), "outbox_path": str(self._outbox)}

    def sync(self, wait: bool = False) -> Dict[str, Any]:
        """One sync cycle; prints and returns the report."""
        report = ac.config_sync_run(self._server.url, _USER, wait=wait, **self._options())
        print(f"  {self.name:<8} {report['state']:<9} revision={report['revision']}"
              f" pending={report['pending']} conflicts={report['conflicts']}")
        return report

    def status(self) -> Dict[str, Any]:
        """The recorded status; no network."""
        return ac.config_sync_status(self._server.url, _USER, str(self._outbox))

    def resolve(self, key: str, choice: int) -> Dict[str, Any]:
        """Keep candidate number ``choice`` of a conflicted script."""
        return ac.config_sync_resolve(self._server.url, _USER, "scripts", key, choice,
                                      **self._options())

    def write(self, name: str, actions: List[Any]) -> None:
        """Save an action script in this machine's folder."""
        (self.scripts / name).write_text(json.dumps(actions), encoding="utf-8")

    def read(self, name: str) -> Optional[List[Any]]:
        """The script's actions, or ``None`` when this machine does not have it."""
        path = self.scripts / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _walkthrough(root: Path) -> Tuple[List[str], Dict[str, Any]]:
    store_path = root / "server" / "config_sync.sqlite3"
    server = LoopbackServer(store_path)
    server.start()
    laptop, desktop = Machine("laptop", root, server), Machine("desktop", root, server)
    seen: Dict[str, Any] = {}
    try:
        print("1. a script written on the laptop reaches the desktop")
        laptop.write("login.json", [["AC_set_var", {"name": "user", "value": "alice"}]])
        laptop.sync()
        desktop.sync()
        seen["arrived"] = desktop.read("login.json")

        print("2. the server restarts; the bucket is still there")
        committed = ac.ConfigStore(store_path).revision(_USER)
        server.stop()
        server.start()
        seen["restart"] = (committed, ac.ConfigStore(store_path).revision(_USER))

        print("3. the laptop works offline; the change waits in its outbox")
        server.stop()
        laptop.write("report.json", [["AC_set_var", {"name": "mode", "value": "daily"}]])
        seen["offline"] = laptop.sync()
        server.start()
        # A failed send backs off (2 s, doubling, capped at 5 min). A run inside
        # that window does not contact the server and says "offline" again with
        # error "waiting to retry after an earlier failure"; wait=True sleeps
        # through the back-off instead, which is what a scheduled sync wants.
        seen["early"] = laptop.sync()
        seen["back_online"] = laptop.sync(wait=True)

        print("4. both machines edit login.json apart: neither edit is dropped")
        desktop.sync()
        laptop.write("login.json", [["AC_set_var", {"name": "user", "value": "from-laptop"}]])
        desktop.write("login.json", [["AC_set_var", {"name": "user", "value": "from-desktop"}]])
        laptop.sync()
        seen["conflict"] = desktop.sync()
        details = desktop.status()["conflict_details"]
        for detail in details:
            origins = [choice["origin"] for choice in detail["choices"]]
            print(f"     {detail['section']}/{detail['key']}: choose between {origins}")
        seen["details"] = details

        print("5. a person picks the laptop's version on the desktop; both converge")
        if details:
            choices = [choice["origin"] for choice in details[0]["choices"]]
            desktop.resolve(details[0]["key"], choices.index("laptop"))
        seen["resolved"] = desktop.sync()
        laptop.sync()
        seen["final"] = (laptop.read("login.json"), desktop.read("login.json"))
    finally:
        server.stop()
    return _check(seen), seen


def _check(seen: Dict[str, Any]) -> List[str]:
    problems = []
    if seen.get("arrived") != [["AC_set_var", {"name": "user", "value": "alice"}]]:
        problems.append("the laptop's script did not reach the desktop")
    committed, reopened = seen.get("restart", (0, -1))
    if committed < 1 or committed != reopened:
        problems.append(f"revision {committed} became {reopened} across the restart")
    if seen.get("offline", {}).get("state") != "offline" or not seen["offline"]["pending"]:
        problems.append("an unreachable server should leave the change pending")
    if seen.get("back_online", {}).get("state") != "synced":
        problems.append("the queued change was not sent once the server came back")
    if seen.get("conflict", {}).get("state") != "conflict" or not seen.get("details"):
        problems.append("edits made apart should be reported as a conflict")
    if seen.get("resolved", {}).get("state") != "synced":
        problems.append("the resolved conflict did not sync")
    wanted = [["AC_set_var", {"name": "user", "value": "from-laptop"}]]
    if seen.get("final") != (wanted, wanted):
        problems.append(f"the machines did not converge on the chosen version: {seen.get('final')}")
    return problems


def validate() -> int:
    """Run the two-machine walkthrough in a temp directory and check each step."""
    with tempfile.TemporaryDirectory(prefix="ac_config_sync_") as folder:
        problems, _seen = _walkthrough(Path(folder))
    for problem in problems:
        print(f"FAILED: {problem}")
    print("validate:", "failed" if problems else "ok")
    return 1 if problems else 0


def main(argv: Optional[List[str]] = None) -> int:
    """Parse the command line; see the module docstring."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--validate", action="store_true",
                        help="two machines, a temp store and a 127.0.0.1 stand-in server")
    parser.add_argument("--server", help="sync server URL, e.g. http://127.0.0.1:8765")
    parser.add_argument("--user", help="the account whose bucket to use")
    parser.add_argument("--scripts-dir", help="also sync the *.json scripts in this folder")
    parser.add_argument("--run", action="store_true",
                        help="REAL SYNC: reads and writes this machine's hotkeys, triggers, "
                             "address book (and --scripts-dir)")
    args = parser.parse_args(argv)
    if args.validate:
        return validate()
    if not (args.server and args.user):
        parser.error("give --server and --user, or use --validate")
    if args.run:
        options = {"scripts_dir": args.scripts_dir} if args.scripts_dir else {}
        print(json.dumps(ac.config_sync_run(args.server, args.user, **options), indent=2))
    else:
        print(json.dumps(ac.config_sync_status(args.server, args.user), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
