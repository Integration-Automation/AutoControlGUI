"""Phase 7.1: sanity checks on the docker/ scaffold.

We can't actually run Docker in CI, but we can:
- verify the files exist and are parseable
- assert the entrypoint covers every documented mode
- assert the compose file references the built image and the published ports
"""
from pathlib import Path

import pytest


_DOCKER_DIR = Path(__file__).resolve().parents[3] / "docker"


def test_dockerfile_exists_and_uses_python_base():
    raw = (_DOCKER_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:" in raw
    assert "xvfb" in raw.lower()
    assert "EXPOSE" in raw
    # Must pin the entrypoint script we ship alongside.
    assert "autocontrol-entrypoint" in raw


def test_entrypoint_handles_every_documented_mode():
    raw = (_DOCKER_DIR / "entrypoint.sh").read_text(encoding="utf-8")
    for mode in ("rest", "remote-host", "signaling", "shell"):
        # Shell case branches don't quote, just look for ``rest)`` etc.
        assert f"\n    {mode})" in raw, \
            f"entrypoint missing case branch for {mode}"
    assert "Xvfb" in raw
    assert "DISPLAY" in raw


def test_compose_file_declares_three_services():
    raw = (_DOCKER_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    for svc in ("rest:", "remote-host:", "signaling:"):
        assert svc in raw, f"compose missing service {svc}"
    assert "autocontrol:latest" in raw
    # Each service should declare a port mapping.
    assert "9939:9939" in raw
    assert "9940:9940" in raw
    assert "8765:8765" in raw


def test_dockerignore_keeps_build_context_lean():
    raw = (_DOCKER_DIR / ".dockerignore").read_text(encoding="utf-8")
    # The biggest space-wasters should all be excluded.
    for line in ("test/", "docs/", "__pycache__", "*.egg-info"):
        assert line in raw, f".dockerignore missing {line}"


@pytest.mark.parametrize("expected_port", ["9939", "9940", "8765"])
def test_dockerfile_exposes_each_service_port(expected_port):
    raw = (_DOCKER_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert expected_port in raw
