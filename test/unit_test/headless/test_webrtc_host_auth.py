"""Everything between a viewer's first `auth` message and its first keystroke.

`ViewerAuthMixin` is the half of the WebRTC host that decides whether a peer
that just connected may drive this machine: the token check, the two
auto-approve paths (trust list, IP whitelist), the manual accept/reject the GUI
drives, and the grace period that closes a peer which never authenticates. It
is the security boundary of the whole remote-desktop subsystem, and until the
`[webrtc]` extra became part of the measured install nothing imported it on any
CI square -- `webrtc_transport` raises ImportError at module level without
aiortc, so the module could not even be loaded to be tested.

The mixin's own docstring lists what it needs from the host it is mixed into
(`_token`, `_trust_list`, `_ip_whitelist`, `_authenticated`, `_send_ctrl`,
`_spawn_bg`, `_async_stop`, ...). `_Host` below supplies exactly that list and
nothing else, so a mixin that starts reaching for something new fails here
rather than depending on whatever `WebRTCDesktopHost` happens to also own.

The two collaborators that reach outside the process are replaced: the asyncio
bridge, whose `call_soon` would otherwise queue the work onto a loop no test is
running, and the audit log, which writes to the user's real
`~/.je_auto_control`.
"""
import asyncio

import pytest

from je_auto_control.utils.remote_desktop import webrtc_host_auth as auth_module
from je_auto_control.utils.remote_desktop.permissions import SessionPermissions
from je_auto_control.utils.remote_desktop.trust_list import TrustList
from je_auto_control.utils.remote_desktop.webrtc_host_auth import ViewerAuthMixin


class _ImmediateBridge:
    """The asyncio bridge, minus the loop: run the callback where it is made."""

    def __init__(self) -> None:
        self.deferred = []

    def call_soon(self, callback) -> None:
        self.deferred.append(callback)
        callback()


class _AuditLog:
    def __init__(self) -> None:
        self.events = []

    def log(self, event_type, **fields) -> None:
        self.events.append((event_type, fields))


class _Host(ViewerAuthMixin):
    """A host with exactly the attributes the mixin's docstring asks for."""

    def __init__(self, *, token="secret", trust_list=None, ip_whitelist=None,
                 remote_ip=None, permissions=None, on_pending_viewer=None):
        self._token = token
        self._trust_list = trust_list
        self._ip_whitelist = list(ip_whitelist or [])
        self._permissions = permissions or SessionPermissions.full_control()
        self._remote_ip = remote_ip
        self._authenticated = False
        self._has_pending_viewer = False
        self._pending_viewer_id = None
        self._auth_deadline_handle = None
        self._on_authenticated = None
        self._on_pending_viewer = on_pending_viewer
        self.sent = []
        self.stopped = 0
        self.spawned = []

    def _send_ctrl(self, message):
        self.sent.append(message)

    def _spawn_bg(self, coroutine):
        coroutine.close()          # never awaited here; do not leak the frame
        self.spawned.append(coroutine)
        return coroutine

    async def _async_stop(self):
        self.stopped += 1

    def types_sent(self):
        return [message["type"] for message in self.sent]


@pytest.fixture
def bridge(monkeypatch):
    """Replace the asyncio bridge and the audit log for the whole module.

    A loop is installed but never run, which is the shape the real bridge
    presents to this code: ``call_soon`` work happens on the loop thread, so
    ``asyncio.get_event_loop()`` resolves there, while anything handed to
    ``call_later`` is still only scheduled when the test looks at it.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    immediate = _ImmediateBridge()
    log = _AuditLog()
    monkeypatch.setattr(auth_module, "get_bridge", lambda: immediate)
    monkeypatch.setattr(auth_module, "default_audit_log", lambda: log)
    monkeypatch.setattr(auth_module, "load_or_create_host_fingerprint",
                        lambda: "f" * 64)
    immediate.audit = log
    immediate.loop = loop
    yield immediate
    asyncio.set_event_loop(None)
    loop.close()


# === The token is the gate ==================================================

@pytest.mark.parametrize("token", ["wrong", "", None, 7, ["secret"]])
def test_a_wrong_or_malformed_token_never_authenticates(bridge, token):
    """The token arrives from the network; only an equal string may pass."""
    host = _Host(token="secret")
    host._handle_auth({"token": token, "viewer_id": "v1"})
    assert host._authenticated is False
    assert host.types_sent() == ["auth_fail"]


def test_a_missing_token_field_is_a_wrong_token(bridge):
    host = _Host(token="secret")
    host._handle_auth({"viewer_id": "v1"})
    assert host.types_sent() == ["auth_fail"]


def test_a_rejected_viewer_is_audited_and_then_disconnected(bridge):
    host = _Host(token="secret", remote_ip="10.0.0.9")
    host._handle_auth({"token": "wrong", "viewer_id": "v1"})
    assert [event for event, _ in bridge.audit.events] == ["auth_fail"]
    fields = bridge.audit.events[0][1]
    assert fields["viewer_id"] == "v1"
    assert "10.0.0.9" in fields["detail"]
    # `_schedule_close_after_fail` was handed to the bridge, so the peer is
    # on its way out rather than left holding an unauthenticated channel.
    assert bridge.deferred


def test_the_right_token_with_no_prompt_hook_approves_immediately(bridge):
    """Headless use has no GUI to ask; the token is then the whole check."""
    host = _Host(token="secret")
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    assert host._authenticated is True
    assert host.types_sent() == ["auth_ok"]


def test_the_right_token_with_a_prompt_hook_waits_for_a_person(bridge):
    asked = []
    host = _Host(token="secret", on_pending_viewer=lambda: asked.append(True))
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    assert asked == [True]
    assert host.has_pending_viewer is True
    assert host._authenticated is False
    assert host.types_sent() == []


def test_a_prompt_hook_that_throws_leaves_the_viewer_pending(bridge):
    """A broken GUI callback must not authenticate the peer by accident."""
    def explode():
        raise RuntimeError("no window")

    host = _Host(token="secret", on_pending_viewer=explode)
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    assert host._authenticated is False
    assert host.has_pending_viewer is True


def test_a_non_string_viewer_id_is_recorded_as_absent(bridge):
    host = _Host(token="secret", on_pending_viewer=lambda: None)
    host._handle_auth({"token": "secret", "viewer_id": 7})
    assert host.pending_viewer_id is None


# === Auto-approve by trust list =============================================

def test_a_trusted_viewer_skips_the_prompt(bridge, tmp_path):
    trust = TrustList(tmp_path / "trusted.json")
    trust.add("v1", label="office laptop")
    asked = []
    host = _Host(token="secret", trust_list=trust,
                 on_pending_viewer=lambda: asked.append(True))
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    assert asked == []
    assert host._authenticated is True
    assert trust.list_entries()[0]["last_used"] is not None


def test_an_untrusted_viewer_still_gets_the_prompt(bridge, tmp_path):
    trust = TrustList(tmp_path / "trusted.json")
    trust.add("someone-else")
    asked = []
    host = _Host(token="secret", trust_list=trust,
                 on_pending_viewer=lambda: asked.append(True))
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    assert asked == [True]
    assert host._authenticated is False


def test_a_trust_list_that_throws_does_not_auto_approve(bridge):
    """Fail closed: an unreadable trust store trusts nobody."""
    class _Broken:
        def is_trusted(self, viewer_id):
            raise OSError("disk gone")

    asked = []
    host = _Host(token="secret", trust_list=_Broken(),
                 on_pending_viewer=lambda: asked.append(True))
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    assert host._authenticated is False
    assert asked == [True]


def test_trusting_the_pending_viewer_adds_it_and_approves(bridge, tmp_path):
    trust = TrustList(tmp_path / "trusted.json")
    host = _Host(token="secret", trust_list=trust,
                 on_pending_viewer=lambda: None)
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    host.trust_pending_viewer(label="lab machine")
    assert trust.is_trusted("v1") is True
    assert trust.list_entries()[0]["label"] == "lab machine"
    assert host._authenticated is True


def test_trusting_with_no_trust_list_still_approves(bridge):
    host = _Host(token="secret", on_pending_viewer=lambda: None)
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    host.trust_pending_viewer()
    assert host._authenticated is True


# === Auto-approve by IP whitelist ===========================================

@pytest.mark.parametrize("remote_ip, allowed", [
    ("10.0.0.5", True),
    ("10.0.1.5", False),
    ("192.168.1.7", True),
    ("::1", False),
])
def test_the_whitelist_matches_by_network_not_by_string(bridge, remote_ip,
                                                        allowed):
    asked = []
    host = _Host(token="secret", remote_ip=remote_ip,
                 ip_whitelist=["10.0.0.0/24", " 192.168.1.7 "],
                 on_pending_viewer=lambda: asked.append(True))
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    assert host._authenticated is allowed
    assert asked == ([] if allowed else [True])


def test_an_ipv6_peer_matches_an_ipv6_whitelist(bridge):
    host = _Host(token="secret", remote_ip="fd00::5",
                 ip_whitelist=["fd00::/8"], on_pending_viewer=lambda: None)
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    assert host._authenticated is True


@pytest.mark.parametrize("whitelist", [["not-a-cidr"], ["10.0.0.0/99"], []])
def test_an_unparseable_whitelist_entry_is_skipped_not_fatal(bridge,
                                                             whitelist):
    host = _Host(token="secret", remote_ip="10.0.0.5",
                 ip_whitelist=whitelist, on_pending_viewer=lambda: None)
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    assert host._authenticated is False


@pytest.mark.parametrize("remote_ip", [None, "", "not-an-address"])
def test_a_peer_with_no_usable_address_never_matches(bridge, remote_ip):
    host = _Host(token="secret", remote_ip=remote_ip,
                 ip_whitelist=["0.0.0.0/0"], on_pending_viewer=lambda: None)
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    assert host._authenticated is False


# === What approval and rejection actually send ==============================

def test_approval_tells_the_viewer_what_it_may_do(bridge):
    host = _Host(token="secret",
                 permissions=SessionPermissions.view_only(),
                 on_pending_viewer=lambda: None)
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    host.approve_pending_viewer()
    message = host.sent[-1]
    assert message["type"] == "auth_ok"
    assert message["read_only"] is True
    assert message["permissions"]["allow_input"] is False
    assert message["fingerprint"] == "f" * 64


def test_approval_is_audited_and_cancels_the_grace_period(bridge):
    class _Handle:
        cancelled = False

        def cancel(self):
            self.cancelled = True

    handle = _Handle()
    host = _Host(token="secret", remote_ip="10.0.0.9",
                 on_pending_viewer=lambda: None)
    host._auth_deadline_handle = handle
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    host.approve_pending_viewer()
    assert handle.cancelled is True
    assert host._auth_deadline_handle is None
    assert [event for event, _ in bridge.audit.events] == ["auth_ok"]


def test_the_authenticated_callback_runs_and_its_failure_is_contained(bridge):
    called = []
    host = _Host(token="secret", on_pending_viewer=lambda: None)
    host._on_authenticated = lambda: called.append(True)
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    host.approve_pending_viewer()
    assert called == [True]

    def explode():
        raise RuntimeError("gui gone")

    other = _Host(token="secret", on_pending_viewer=lambda: None)
    other._on_authenticated = explode
    other._handle_auth({"token": "secret", "viewer_id": "v2"})
    other.approve_pending_viewer()
    assert other._authenticated is True


def test_approving_twice_does_not_re_send_auth_ok(bridge):
    """The GUI can double-click; the viewer must not see two sessions open."""
    host = _Host(token="secret", on_pending_viewer=lambda: None)
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    host.approve_pending_viewer()
    host.approve_pending_viewer()
    assert host.types_sent() == ["auth_ok"]


def test_rejecting_the_pending_viewer_fails_and_closes(bridge):
    host = _Host(token="secret", on_pending_viewer=lambda: None)
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    host.reject_pending_viewer()
    assert host.types_sent() == ["auth_fail"]
    assert host.has_pending_viewer is False
    assert host._authenticated is False


# === The grace period =======================================================

def test_the_deadline_closes_a_peer_that_never_authenticated(bridge):
    host = _Host(token="secret", on_pending_viewer=lambda: None)
    host._enforce_auth_deadline()
    assert host.spawned, "an unauthenticated peer must be stopped"


def test_the_deadline_leaves_an_authenticated_peer_alone(bridge):
    host = _Host(token="secret")
    host._handle_auth({"token": "secret", "viewer_id": "v1"})
    host._enforce_auth_deadline()
    assert host.spawned == []


# === The secure attention sequence ==========================================

def test_a_successful_sas_is_reported_to_the_viewer(bridge, monkeypatch):
    import je_auto_control.utils.remote_desktop.session_actions as actions
    monkeypatch.setattr(actions, "send_secure_attention_sequence",
                        lambda: None)
    host = _Host(token="secret")
    host._handle_send_sas()
    assert host.types_sent() == ["sas_ok"]


def test_a_platform_that_cannot_send_sas_says_so_rather_than_raising(
        bridge, monkeypatch):
    import je_auto_control.utils.remote_desktop.session_actions as actions

    def unsupported():
        raise RuntimeError("SendSAS is Windows-only")

    monkeypatch.setattr(actions, "send_secure_attention_sequence", unsupported)
    host = _Host(token="secret")
    host._handle_send_sas()
    assert host.types_sent() == ["sas_fail"]
    assert "Windows-only" in host.sent[-1]["error"]
