"""Headless tests for the email-send action (send_email / AC_send_email).

No real SMTP server is contacted: smtplib.SMTP / SMTP_SSL are replaced
with a fake that records the message and the calls made.
"""
import pytest

import je_auto_control as ac
from je_auto_control.utils.email_send import email_sender


class _FakeSMTP:
    """Records send_message / starttls / login without any network I/O."""

    instances = []

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout = host, port, timeout
        self.started_tls = False
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, username, password):
        self.logged_in = (username, password)

    def send_message(self, mime):
        self.sent = mime


@pytest.fixture(autouse=True)
def _fake_smtp(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(email_sender.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(email_sender.smtplib, "SMTP_SSL", _FakeSMTP)
    return _FakeSMTP


def _msg(**over):
    base = {"sender": "a@x.com", "to": "b@y.com",
            "subject": "Hi", "body": "Body"}
    base.update(over)
    return base


def test_sends_with_starttls_by_default():
    result = ac.send_email(_msg(), {"host": "smtp.x.com"})
    assert result["sent"] is True
    server = _FakeSMTP.instances[-1]
    assert server.started_tls is True
    assert server.sent["Subject"] == "Hi"
    assert server.sent["To"] == "b@y.com"


def test_login_when_credentials_given():
    ac.send_email(_msg(), {"host": "smtp.x.com", "username": "u",
                           "password": "p"})
    assert _FakeSMTP.instances[-1].logged_in == ("u", "p")


def test_ssl_path_skips_starttls():
    ac.send_email(_msg(), {"host": "smtp.x.com", "port": 465,
                           "use_ssl": True})
    server = _FakeSMTP.instances[-1]
    assert server.port == 465
    assert server.started_tls is False


def test_multiple_recipients_and_cc():
    ac.send_email(_msg(to=["b@y.com", "c@y.com"], cc="d@y.com"),
                  {"host": "smtp.x.com"})
    server = _FakeSMTP.instances[-1]
    assert server.sent["To"] == "b@y.com, c@y.com"
    assert server.sent["Cc"] == "d@y.com"


def test_attachment_is_added(tmp_path):
    attach = tmp_path / "report.txt"
    attach.write_text("hello", encoding="utf-8")
    ac.send_email(_msg(attachments=[str(attach)]), {"host": "smtp.x.com"})
    mime = _FakeSMTP.instances[-1].sent
    names = [part.get_filename() for part in mime.iter_attachments()]
    assert "report.txt" in names


def test_missing_attachment_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ac.send_email(_msg(attachments=[str(tmp_path / "nope.txt")]),
                      {"host": "smtp.x.com"})


def test_missing_sender_or_recipient_raises():
    with pytest.raises(ValueError):
        ac.send_email({"subject": "x"}, {"host": "smtp.x.com"})


def test_missing_host_raises():
    with pytest.raises(ValueError):
        ac.send_email(_msg(), {})


def test_facade_executor_and_mcp_wiring():
    assert ac.send_email is email_sender.send_email
    assert "AC_send_email" in ac.executor.known_commands()
    record = ac.execute_action(
        [["AC_send_email", {"message": _msg(), "smtp": {"host": "smtp.x.com"}}]])
    assert any("sent" in str(value) for value in record.values())
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {tool.name for tool in build_default_tool_registry()}
    assert "ac_send_email" in names
