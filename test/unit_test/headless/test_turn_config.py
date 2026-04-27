"""Tests for the coturn config bundle generator (round 22)."""
from je_auto_control.utils.remote_desktop.turn_config import (
    main as turn_main,
    render_docker_compose, render_readme, render_systemd_unit,
    render_turnserver_conf, write_bundle,
)


def test_turnserver_conf_contains_required_fields():
    body = render_turnserver_conf(
        realm="example.com", listen_port=3478, tls_port=5349,
        user="alice", secret="HUNTER2",
    )
    assert "realm=example.com" in body
    assert "listening-port=3478" in body
    assert "user=alice:HUNTER2" in body
    assert "lt-cred-mech" in body


def test_turnserver_conf_with_tls_includes_cert_lines():
    body = render_turnserver_conf(
        realm="r", listen_port=3478, tls_port=5349,
        user="u", secret="s",
        tls_cert="/etc/letsencrypt/cert.pem",
        tls_key="/etc/letsencrypt/key.pem",
    )
    assert "tls-listening-port=5349" in body
    assert "cert=/etc/letsencrypt/cert.pem" in body
    assert "pkey=/etc/letsencrypt/key.pem" in body


def test_turnserver_conf_omits_tls_lines_when_no_cert():
    body = render_turnserver_conf(
        realm="r", listen_port=3478, tls_port=5349, user="u", secret="s",
    )
    assert "tls-listening-port" not in body
    assert "cert=" not in body


def test_systemd_unit_references_conf_path():
    unit = render_systemd_unit(conf_path="/etc/turnserver.conf")
    assert "ExecStart=/usr/bin/turnserver -c /etc/turnserver.conf" in unit
    assert "[Service]" in unit and "[Install]" in unit


def test_docker_compose_uses_host_network():
    """coturn relays UDP — bridge mode is wrong; must be host networking."""
    compose = render_docker_compose(
        conf_path="/srv/turnserver.conf", listen_port=3478, tls_port=5349,
    )
    assert "network_mode: host" in compose
    assert "/srv/turnserver.conf:/etc/coturn/turnserver.conf:ro" in compose


def test_readme_picks_turns_scheme_when_tls():
    body = render_readme(
        realm="example.com", listen_port=3478, tls_port=5349,
        user="alice", secret="HUNTER2", tls=True,
    )
    assert "turns:example.com:5349" in body


def test_readme_picks_turn_scheme_when_no_tls():
    body = render_readme(
        realm="example.com", listen_port=3478, tls_port=5349,
        user="alice", secret="HUNTER2", tls=False,
    )
    assert "turn:example.com:3478" in body


def test_write_bundle_creates_all_four_files(tmp_path):
    out = tmp_path / "bundle"
    write_bundle(
        out, realm="r", user="u", secret="s",
        listen_port=3478, tls_port=5349,
        tls_cert=None, tls_key=None, external_ip=None,
    )
    files = sorted(p.name for p in out.iterdir())
    assert files == [
        "README.txt", "coturn.service", "docker-compose.yml", "turnserver.conf",
    ]


def test_cli_main_writes_bundle(tmp_path):
    out = tmp_path / "bundle"
    rc = turn_main([
        "--realm", "turn.example.com",
        "--user", "alice", "--secret", "SECRET123",
        "--output-dir", str(out),
    ])
    assert rc == 0
    body = (out / "turnserver.conf").read_text(encoding="utf-8")
    assert "realm=turn.example.com" in body
    assert "user=alice:SECRET123" in body


def test_cli_main_auto_generates_secret_when_missing(tmp_path):
    out = tmp_path / "bundle"
    rc = turn_main([
        "--realm", "r", "--user", "u",
        "--output-dir", str(out),
    ])
    assert rc == 0
    body = (out / "turnserver.conf").read_text(encoding="utf-8")
    # Auto-generated tokens are URL-safe random, so the user line is present
    # but with an opaque non-empty secret.
    user_line = next(
        line for line in body.splitlines() if line.startswith("user=u:")
    )
    secret = user_line.split(":", 1)[1]
    assert len(secret) >= 16  # token_urlsafe(24) → ~32 chars
