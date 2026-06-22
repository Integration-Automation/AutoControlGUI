"""Tests for cross-platform desktop notifications."""
from je_auto_control.utils.notify import notifier


def test_notify_spec_linux_uses_notify_send():
    argv, env = notifier._notify_spec("Linux", "Title", "Body")
    assert argv[0] == "notify-send"
    assert "Title" in argv and "Body" in argv
    assert env == {}


def test_notify_spec_macos_passes_strings_via_env():
    argv, env = notifier._notify_spec("Darwin", "Title", "Body")
    assert argv[0] == "osascript"
    # Strings travel through env, never the command line (no injection).
    assert "Title" not in " ".join(argv)
    assert env["AC_NOTIFY_TITLE"] == "Title"
    assert env["AC_NOTIFY_MSG"] == "Body"


def test_notify_spec_windows_passes_strings_via_env():
    argv, env = notifier._notify_spec("Windows", "Title", "Body")
    assert argv[0] == "powershell"
    assert "Title" not in " ".join(argv)
    assert env["AC_NOTIFY_TITLE"] == "Title"


def test_notify_spec_unsupported_platform_returns_none():
    argv, _env = notifier._notify_spec("Plan9", "T", "M")
    assert argv is None


def test_notify_runs_and_reports_shown(monkeypatch):
    calls = {}

    def fake_run(argv, **kwargs):
        calls["argv"] = argv
        calls["env"] = kwargs.get("env")

    monkeypatch.setattr(notifier.subprocess, "run", fake_run)
    result = notifier.notify("Done", "All good", system="Linux")
    assert result.shown is True
    assert calls["argv"][0] == "notify-send"


def test_notify_unsupported_platform_is_not_shown():
    assert notifier.notify("x", "y", system="Plan9").shown is False


def test_notify_missing_tool_is_handled(monkeypatch):
    def boom(argv, **kwargs):
        raise FileNotFoundError("notify-send")

    monkeypatch.setattr(notifier.subprocess, "run", boom)
    result = notifier.notify("x", "y", system="Linux")
    assert result.shown is False
    assert "FileNotFoundError" in result.detail
