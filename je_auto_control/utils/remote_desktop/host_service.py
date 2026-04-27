"""Headless WebRTC host runner + multi-platform service installer.

The runner is a thin wrapper around :class:`MultiViewerHost` that loads a
JSON config and either:
  * publishes once via the signaling server and waits for viewers
    (useful for one-shot scripts), or
  * loops indefinitely as a daemon (publish → wait answer → re-publish),
    which is what the OS service entry point calls.

Per-platform service installation is exposed as CLI subcommands:
  * Windows: ``install`` / ``uninstall`` via pywin32 (lazy-imported)
  * macOS:   ``generate-launchd PATH`` writes a launchd plist to PATH
  * Linux:   ``generate-systemd PATH`` writes a systemd unit to PATH

The macOS / Linux generators emit the unit and stop — the user runs
``launchctl load`` / ``systemctl --user enable`` themselves so we never
silently elevate privileges. Configuration lives at
``~/.je_auto_control/host_service.json``.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


_DEFAULT_CONFIG_PATH = (
    Path(os.path.expanduser("~")) / ".je_auto_control" / "host_service.json"
)


@dataclass
class HostServiceConfig:
    """JSON shape for the daemon's config file."""
    token: str
    server_url: str
    host_id: str
    server_secret: Optional[str] = None
    monitor_index: int = 1
    fps: int = 24
    read_only: bool = False
    show_cursor: bool = True
    poll_interval_s: float = 2.0


def load_config(path: Optional[Path] = None) -> HostServiceConfig:
    target = Path(path) if path else _DEFAULT_CONFIG_PATH
    if not target.exists():
        raise FileNotFoundError(f"service config not found: {target}")
    raw = json.loads(target.read_text(encoding="utf-8"))
    required = ("token", "server_url", "host_id")
    missing = [k for k in required if not raw.get(k)]
    if missing:
        raise ValueError(f"config missing required fields: {missing}")
    return HostServiceConfig(
        token=raw["token"],
        server_url=raw["server_url"],
        host_id=raw["host_id"],
        server_secret=raw.get("server_secret"),
        monitor_index=int(raw.get("monitor_index", 1)),
        fps=int(raw.get("fps", 24)),
        read_only=bool(raw.get("read_only", False)),
        show_cursor=bool(raw.get("show_cursor", True)),
        poll_interval_s=float(raw.get("poll_interval_s", 2.0)),
    )


def write_default_config(path: Optional[Path] = None) -> Path:
    """Write a stub config the user must edit before installing."""
    target = Path(path) if path else _DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    template = {
        "token": "CHANGE_ME_BEFORE_USE",  # nosec B105  # NOSONAR python:S6418  # reason: placeholder in stub config the user MUST edit before installing the service
        "server_url": "https://your-signaling-server.example.com",
        "host_id": "abcd1234",
        "server_secret": None,  # nosec B105  # reason: explicit None placeholder
        "monitor_index": 1,
        "fps": 24,
        "read_only": False,
        "show_cursor": True,
        "poll_interval_s": 2.0,
    }
    target.write_text(json.dumps(template, indent=2), encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target


def run_daemon(config: HostServiceConfig) -> None:
    """Block forever: publish offer → wait for answer → accept → loop."""
    from je_auto_control.utils.remote_desktop import (
        WebRTCConfig, default_trust_list, signaling_client,
    )
    from je_auto_control.utils.remote_desktop.multi_viewer import MultiViewerHost

    multi = MultiViewerHost(
        token=config.token,
        config=WebRTCConfig(
            monitor_index=config.monitor_index,
            fps=config.fps,
            show_cursor=config.show_cursor,
        ),
        trust_list=default_trust_list(),
        read_only=config.read_only,
    )
    autocontrol_logger.info(
        "host_service: daemon up; host_id=%s server=%s",
        config.host_id, config.server_url,
    )
    while True:
        try:
            session_id, offer = multi.create_session_offer()
            signaling_client.push_offer(
                config.server_url, config.host_id, offer,
                secret=config.server_secret,
            )
            answer = signaling_client.wait_for_answer(
                config.server_url, config.host_id,
                secret=config.server_secret,
                timeout_s=300.0,
            )
            multi.accept_session_answer(session_id, answer)
            autocontrol_logger.info(
                "host_service: viewer connected to session %s (%d total)",
                session_id, multi.session_count(),
            )
            time.sleep(config.poll_interval_s)
        except (signaling_client.SignalingError, OSError, RuntimeError) as error:
            autocontrol_logger.warning("host_service loop: %r", error)
            time.sleep(min(30.0, config.poll_interval_s * 5))
        except KeyboardInterrupt:
            autocontrol_logger.info("host_service: shutting down")
            multi.stop_all()
            return


# --- service installation helpers ----------------------------------------


def _generate_launchd_plist(config_path: Path, output_path: Path) -> None:
    python = sys.executable
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.je_auto_control.remote_host</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>-m</string>
        <string>je_auto_control.utils.remote_desktop.host_service</string>
        <string>run</string>
        <string>--config</string>
        <string>{config_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{Path.home()}/Library/Logs/je_auto_control_host.log</string>
    <key>StandardErrorPath</key>
    <string>{Path.home()}/Library/Logs/je_auto_control_host.err</string>
</dict>
</plist>
"""
    output_path.write_text(plist, encoding="utf-8")


def _generate_systemd_unit(config_path: Path, output_path: Path) -> None:
    python = sys.executable
    unit = f"""[Unit]
Description=AutoControl WebRTC remote-desktop host
After=network.target

[Service]
Type=simple
ExecStart={python} -m je_auto_control.utils.remote_desktop.host_service run --config {config_path}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""
    output_path.write_text(unit, encoding="utf-8")


def _interactive_configure() -> int:
    """Prompt the user for the four required fields and write a config."""
    print("AutoControl host service — interactive configuration")
    print(f"Config will be written to: {_DEFAULT_CONFIG_PATH}")
    answers = {}
    answers["token"] = input("Auth token (shared with viewers): ").strip()
    answers["server_url"] = input("Signaling server URL: ").strip()
    answers["host_id"] = input("Host ID: ").strip()
    secret = input("Server secret (blank if none): ").strip()
    answers["server_secret"] = secret or None
    monitor = input("Monitor index (default 1): ").strip() or "1"
    answers["monitor_index"] = int(monitor)
    fps = input("Target FPS (default 24): ").strip() or "24"
    answers["fps"] = int(fps)
    answers["read_only"] = input("Read-only? (y/N): ").strip().lower() == "y"
    answers["show_cursor"] = (
        input("Show cursor in stream? (Y/n): ").strip().lower() != "n"
    )
    answers["poll_interval_s"] = 2.0
    _DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DEFAULT_CONFIG_PATH.write_text(
        json.dumps(answers, indent=2), encoding="utf-8",
    )
    try:
        os.chmod(_DEFAULT_CONFIG_PATH, 0o600)
    except OSError:
        pass
    print(f"Wrote {_DEFAULT_CONFIG_PATH}")
    return 0


def _print_status() -> int:
    """Print whether config exists + Windows service state if applicable."""
    if _DEFAULT_CONFIG_PATH.exists():
        try:
            cfg = load_config()
            print(f"Config: {_DEFAULT_CONFIG_PATH}  ({len(cfg.token)}-char token, "
                  f"host_id={cfg.host_id})")
        except (ValueError, OSError) as error:
            print(f"Config exists but invalid: {error}")
    else:
        print(f"No config at {_DEFAULT_CONFIG_PATH} — run 'configure' or 'init'.")
    if sys.platform == "win32":
        import subprocess  # nosec B404  # reason: only invoke fixed sc query argv
        try:
            result = subprocess.run(  # nosec B603 B607  # reason: fixed argv list, no shell
                ["sc", "query", "JeAutoControlRemoteHost"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            if result.returncode == 0:
                print("Windows service status:")
                print(result.stdout)
            else:
                print(
                    "Windows service not installed "
                    "(run install-windows-service)."
                )
        except (OSError, subprocess.SubprocessError) as error:
            print(f"sc query failed: {error}")
    return 0


def _restart_windows_service() -> int:
    if sys.platform != "win32":
        print("restart-windows-service is Windows-only.", file=sys.stderr)
        return 2
    import subprocess  # nosec B404  # reason: only invoke fixed sc stop/start argv
    try:
        subprocess.run(  # nosec B603 B607  # reason: fixed argv list, no shell
            ["sc", "stop", "JeAutoControlRemoteHost"],
            timeout=15, check=False,
        )
        subprocess.run(  # nosec B603 B607  # reason: fixed argv list, no shell
            ["sc", "start", "JeAutoControlRemoteHost"],
            timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"sc command failed: {error}", file=sys.stderr)
        return 1
    print("Service restart requested. Use 'status' to verify.")
    return 0


def _install_windows_service(config_path: Path) -> int:
    # config_path is part of the public install contract — kept on the
    # signature for symmetry with the Linux installer even though the
    # Windows service auto-discovers its config at runtime.
    del config_path  # suppress S1172
    try:
        import win32serviceutil  # type: ignore  # noqa: F401
    except ImportError:
        print("pywin32 is required: pip install pywin32", file=sys.stderr)
        return 2
    # Write the service module to a temp file the service can locate.
    target = Path(sys.prefix) / "Scripts" / "je_auto_control_host_service.py"
    template = (
        "import sys\n"
        "from je_auto_control.utils.remote_desktop.host_service import "
        "_WindowsService\n"
        "if __name__ == '__main__':\n"
        "    import win32serviceutil\n"
        "    win32serviceutil.HandleCommandLine(_WindowsService)\n"
    )
    target.write_text(template, encoding="utf-8")
    print(f"Wrote service entry point: {target}")
    print("Run as Administrator:")
    print(f"  {sys.executable} {target} --startup auto install")
    print(f"  {sys.executable} {target} start")
    return 0


# --- pywin32 service class (lazy) ----------------------------------------

if sys.platform == "win32":  # pragma: no cover - Windows-only
    try:
        import win32event  # type: ignore
        import win32service  # type: ignore
        import win32serviceutil  # type: ignore

        class _WindowsService(win32serviceutil.ServiceFramework):
            _svc_name_ = "JeAutoControlRemoteHost"
            _svc_display_name_ = "AutoControl Remote Desktop Host"
            _svc_description_ = (
                "Headless WebRTC host that publishes this machine "
                "to a signaling server for remote-desktop connections."
            )

            def __init__(self, args) -> None:
                super().__init__(args)
                self._stop_event = win32event.CreateEvent(None, 0, 0, None)
                self._running = True

            def SvcStop(self) -> None:  # noqa: N802 pywin32 API
                self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
                self._running = False
                win32event.SetEvent(self._stop_event)

            def SvcDoRun(self) -> None:  # noqa: N802 pywin32 API
                logging.basicConfig(
                    level=logging.INFO,
                    filename=str(Path(os.path.expanduser("~"))
                                 / ".je_auto_control" / "host_service.log"),
                )
                try:
                    config = load_config()
                except (OSError, ValueError) as error:
                    logging.error("config load failed: %r", error)
                    return
                run_daemon(config)
    except ImportError:
        _WindowsService = None  # type: ignore
else:
    _WindowsService = None  # type: ignore


# --- CLI -----------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="je_auto_control.utils.remote_desktop.host_service",
        description="Headless WebRTC host runner + service installer.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_p = sub.add_parser("init", help="write a default config file")
    init_p.add_argument("--config", type=Path, default=None)

    run_p = sub.add_parser("run", help="run the daemon (foreground)")
    run_p.add_argument("--config", type=Path, default=None)

    sub.add_parser("available-codecs",
                   help="list hardware H.264 codecs PyAV can open")

    sub.add_parser("configure", help="interactive config wizard")
    sub.add_parser("status",
                   help="print service / config status")
    sub.add_parser("restart-windows-service",
                   help="restart the Windows service (admin required)")

    win_p = sub.add_parser("install-windows-service",
                           help="install the Windows service (admin required)")
    win_p.add_argument("--config", type=Path, default=None)

    mac_p = sub.add_parser("generate-launchd",
                           help="emit a launchd plist for macOS")
    mac_p.add_argument("output", type=Path)
    mac_p.add_argument("--config", type=Path, default=None)

    lin_p = sub.add_parser("generate-systemd",
                           help="emit a systemd unit for Linux user services")
    lin_p.add_argument("output", type=Path)
    lin_p.add_argument("--config", type=Path, default=None)
    return parser


def _cmd_init(args) -> int:
    path = write_default_config(args.config)
    print(f"Wrote stub config: {path}")
    print("Edit the file (token, server_url, host_id) before running 'run'.")
    return 0


def _cmd_run(args) -> int:
    config = load_config(args.config)
    run_daemon(config)
    return 0


def _cmd_available_codecs(_args) -> int:
    from je_auto_control.utils.remote_desktop.hw_codec import (
        available_hardware_codecs,
    )
    codecs = available_hardware_codecs()
    if codecs:
        print("Available hardware codecs:")
        for name in codecs:
            print(f"  {name}")
    else:
        print("No hardware H.264 codecs available; will use libx264.")
    return 0


def _cmd_install_windows_service(args) -> int:
    return _install_windows_service(args.config or _DEFAULT_CONFIG_PATH)


def _cmd_generate_launchd(args) -> int:
    _generate_launchd_plist(args.config or _DEFAULT_CONFIG_PATH, args.output)
    print(f"Wrote launchd plist: {args.output}")
    print("Activate with:")
    print(f"  cp {args.output} ~/Library/LaunchAgents/")
    print(f"  launchctl load ~/Library/LaunchAgents/{args.output.name}")
    return 0


def _cmd_generate_systemd(args) -> int:
    _generate_systemd_unit(args.config or _DEFAULT_CONFIG_PATH, args.output)
    print(f"Wrote systemd unit: {args.output}")
    print("Activate with:")
    print(f"  mkdir -p ~/.config/systemd/user && cp {args.output} "
          "~/.config/systemd/user/")
    print(f"  systemctl --user enable --now {args.output.stem}")
    return 0


_COMMAND_DISPATCH = {
    "init": _cmd_init,
    "configure": lambda _args: _interactive_configure(),
    "status": lambda _args: _print_status(),
    "restart-windows-service": lambda _args: _restart_windows_service(),
    "run": _cmd_run,
    "available-codecs": _cmd_available_codecs,
    "install-windows-service": _cmd_install_windows_service,
    "generate-launchd": _cmd_generate_launchd,
    "generate-systemd": _cmd_generate_systemd,
}


def main(argv: Optional[list] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler = _COMMAND_DISPATCH.get(args.command)
    if handler is None:
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
