"""Regression tests for the outbound-integration defects of the 2026-09-23 audit.

urllib carries every header across a redirect, so a cross-host redirect handed
the Authorization header to the other host. The ticket backends and the Slack
bot called urllib directly, skipping the egress policy; a non-object JSON reply
crashed the failure-hook manager and ended the Slack poll loop; and
``/screenshot`` wrote wherever the chat message said.
"""
import http.server
import threading
from unittest.mock import patch

import pytest

from je_auto_control.utils.chatops import handlers, slack_bot
from je_auto_control.utils.chatops.router import ChatOpsError, CommandRouter
from je_auto_control.utils.egress.egress_policy import set_egress_policy
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.failure_hooks.backends import _post_json
from je_auto_control.utils.http_client import http_client


class _Recorder(http.server.BaseHTTPRequestHandler):
    """Redirect ``/redir`` to the other server; record every request's auth."""

    def _handle(self):
        self.server.seen.append((self.command, self.path, self.headers.get("Authorization")))
        if self.path.startswith("/redir"):
            self.send_response(302)
            self.send_header("Location", self.server.redirect_to)
            self.end_headers()
            return
        body = self.server.body
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_POST = _handle

    def log_message(self, *_args):
        pass


@pytest.fixture
def servers():
    started = []

    def start(body=b'{"key": "X-1"}'):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
        server.seen, server.body, server.redirect_to = [], body, ""
        threading.Thread(target=server.serve_forever, daemon=True).start()
        started.append(server)
        return server

    yield start
    for server in started:
        server.shutdown()
        server.server_close()
    set_egress_policy()


def test_a_cross_host_redirect_drops_the_authorization_header(servers):
    first, second = servers(), servers()
    first.redirect_to = f"http://localhost:{second.server_port}/landing"
    http_client.http_request(f"http://127.0.0.1:{first.server_port}/redir",
                             auth={"type": "bearer", "token": "SECRET"}, timeout=5)
    assert first.seen[0][2] == "Bearer SECRET"
    assert second.seen == [("GET", "/landing", None)]


def test_a_same_host_redirect_keeps_it(servers):
    server = servers()
    server.redirect_to = f"http://127.0.0.1:{server.server_port}/landing"
    http_client.http_request(f"http://127.0.0.1:{server.server_port}/redir",
                             auth={"type": "bearer", "token": "SECRET"}, timeout=5)
    assert server.seen[1] == ("GET", "/landing", "Bearer SECRET")


def test_a_ticket_backend_does_not_follow_a_redirect(servers):
    first, second = servers(), servers()
    first.redirect_to = f"http://localhost:{second.server_port}/steal"
    result = _post_json("jira", f"http://127.0.0.1:{first.server_port}/redir/issue",
                        {}, headers={"Authorization": "Basic c2VjcmV0"}, id_key="key")
    assert result.succeeded is False and "302" in result.error
    assert second.seen == []


def test_a_ticket_backend_obeys_the_egress_policy(servers):
    server = servers()
    set_egress_policy(deny=["127.0.0.1"])
    result = _post_json("jira", f"http://127.0.0.1:{server.server_port}/issue",
                        {}, headers={}, id_key="key")
    assert result.succeeded is False and "egress" in result.error
    assert server.seen == []


def test_a_non_object_ticket_reply_is_a_failed_result(servers):
    server = servers(body=b"[]")
    result = _post_json("jira", f"http://127.0.0.1:{server.server_port}/issue",
                        {}, headers={}, id_key="key")
    assert result.succeeded is False and "JSON object" in result.error


def _bot():
    return slack_bot.SlackBot(token="xoxb-test", channel_id="C1", router=CommandRouter())


def test_the_slack_bot_obeys_the_egress_policy():
    set_egress_policy(deny=["slack.com"])
    try:
        with pytest.raises(slack_bot.SlackError, match="egress"):
            _bot()._request("https://slack.com/api/auth.test", method="GET")
    finally:
        set_egress_policy()


def test_a_non_object_slack_reply_does_not_end_the_poll_loop():
    bot = _bot()
    with patch.object(slack_bot, "perform_call", return_value={"status": 200, "json": [1]}):
        bot.run_forever(max_iterations=1)  # must return, not raise


def test_screenshot_keeps_only_the_file_name(tmp_path):
    outside = tmp_path / "elsewhere" / "evil.png"
    with patch("je_auto_control.wrapper.auto_control_screen.screenshot") as shot:
        result = handlers.cmd_screenshot([str(outside)], {"screenshot_dir": str(tmp_path / "shots")})
    assert shot.call_args.kwargs["file_path"] == str(tmp_path / "shots" / "evil.png")
    assert result.artifact_path == str(tmp_path / "shots" / "evil.png")


def test_chatops_errors_are_in_the_framework_family():
    assert issubclass(slack_bot.SlackError, AutoControlException)
    assert issubclass(ChatOpsError, AutoControlException)
