"""Phase 7.1: sanity checks on the docker/ scaffold.

We can't actually run Docker in CI, but we can:
- verify the files exist and are parseable
- assert the entrypoint covers every documented mode
- assert the compose file references the built image and the published ports
"""
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DOCKER_DIR = _REPO_ROOT / "docker"
#: Spelled from ``chr`` so this file stays byte-identical under any
#: checkout normalisation that might rewrite a literal in it.
CRLF = (chr(13) + chr(10)).encode()


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


def test_dockerignore_sits_at_the_build_context_root():
    """Docker reads ``.dockerignore`` from the build *context* root only.

    Every documented build passes the repository root as the context
    (``docker build -f docker/Dockerfile .``), so a copy next to the
    Dockerfile is never read: the whole tree -- .git, .venv, test/ -- is
    shipped to the daemon and the exclusions do nothing.
    """
    assert (_REPO_ROOT / ".dockerignore").is_file(), (
        ".dockerignore must live at the repository root, not in docker/")
    assert not (_DOCKER_DIR / ".dockerignore").exists(), (
        "a docker/.dockerignore is dead weight; Docker never reads it")


def test_dockerignore_keeps_build_context_lean():
    raw = (_REPO_ROOT / ".dockerignore").read_text(encoding="utf-8")
    # The biggest space-wasters should all be excluded.
    for line in ("test/", "docs/", "__pycache__", "*.egg-info"):
        assert line in raw, f".dockerignore missing {line}"


@pytest.mark.parametrize("script", [
    "entrypoint.sh", "entrypoint-xfce.sh", "entrypoint-wayland.sh",
    "entrypoint-seat.sh", "entrypoint-x11.sh",
])
def test_entrypoints_keep_unix_line_endings(script):
    """A CRLF shebang makes an image that builds and then cannot start.

    A carriage return at the end of the shebang sends the kernel looking
    for an interpreter whose name ends in one, and every container dies
    with the useless ``exec ...: no such file or directory``.
    ``.gitattributes`` pins ``*.sh text eol=lf`` so a Windows checkout
    cannot reintroduce it; this fails if that pin is ever dropped.
    """
    path = _DOCKER_DIR / script
    if not path.exists():  # optional variants stay optional
        pytest.skip(f"{script} not present")
    assert CRLF not in path.read_bytes(), (
        f"{script} has CRLF line endings; its container cannot exec /bin/sh")


@pytest.mark.parametrize("expected_port", ["9939", "9940", "8765"])
def test_dockerfile_exposes_each_service_port(expected_port):
    raw = (_DOCKER_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert expected_port in raw


# --- XFCE variant ---------------------------------------------------

def test_xfce_dockerfile_exists_and_includes_xfce_and_vnc():
    raw = (_DOCKER_DIR / "Dockerfile.xfce").read_text(encoding="utf-8")
    assert "FROM python:" in raw
    assert "xfce4" in raw.lower()
    assert "x11vnc" in raw
    # Exposes the VNC port on top of the slim image's ports.
    assert "5900" in raw
    for port in ("9939", "9940", "8765"):
        assert port in raw


def test_xfce_entrypoint_starts_xvfb_xfce_vnc():
    raw = (_DOCKER_DIR / "entrypoint-xfce.sh").read_text(encoding="utf-8")
    for tool in ("Xvfb", "startxfce4", "x11vnc"):
        assert tool in raw, f"xfce entrypoint missing {tool}"
    for mode in ("rest", "remote-host", "signaling", "shell"):
        assert f"\n    {mode})" in raw, \
            f"xfce entrypoint missing case branch for {mode}"


# --- CI templates ---------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_github_actions_docker_workflow_exists():
    raw = (_REPO_ROOT / ".github" / "workflows" / "docker.yml").read_text(
        encoding="utf-8",
    )
    assert "docker/setup-buildx-action" in raw
    assert "autocontrol:ci" in raw
    assert "headless-tests" in raw
    # Workflow must execute pytest, not just build the image.
    assert "pytest" in raw


def test_ydotool_verification_image_and_script_exist():
    """The ydotool path is only verified while these two files are wired up."""
    dockerfile = (_DOCKER_DIR / "Dockerfile.ydotool").read_text(
        encoding="utf-8")
    # ydotool 1.0 replaced the CLI; trixie ships none and bookworm ships
    # 0.1.8, so the image has to pull the one under test from unstable.
    assert "sid" in dockerfile
    assert "ydotool" in dockerfile
    assert "ydotool_verify.py" in dockerfile

    script = (_DOCKER_DIR / "ydotool_verify.py").read_text(encoding="utf-8")
    # Reading the kernel device back is the whole point; a version that only
    # checks exit codes would pass against the CLI that exits 0 and emits
    # nothing, which is the bug this exists for.
    assert "/dev/input" in script
    assert "input_event" in script


def test_ydotool_verification_job_grants_uinput_and_the_input_cgroup():
    """--device cannot cover a node ydotoold creates after the container starts."""
    raw = (_REPO_ROOT / ".github" / "workflows" / "docker.yml").read_text(
        encoding="utf-8",
    )
    assert "ydotool-verification" in raw
    assert "modprobe uinput" in raw
    assert "--device /dev/uinput" in raw
    assert "c 13:* rmw" in raw


def test_seat_verification_image_and_script_exist():
    """The one image where an injected event reaches a compositor.

    The other two Wayland images each hold one half still: the capture image
    runs a compositor that consumes no input, the ydotool image reads the
    kernel with no compositor. This one needs all four of the settings that
    join them, and dropping any of them turns the verification into a
    measurement of an empty seat that still passes.
    """
    dockerfile = (_DOCKER_DIR / "Dockerfile.seat").read_text(encoding="utf-8")
    for setting in ("WLR_BACKENDS=headless,libinput",
                    "LIBSEAT_BACKEND=builtin",
                    "SEATD_VTBOUND=0"):
        assert setting in dockerfile, f"Dockerfile.seat missing {setting}"
    # libinput enumerates through udev, not through /dev, so udevd has to be
    # in the image or sway comes up holding nothing.
    assert "udev" in dockerfile
    assert "seat_verify.py" in dockerfile

    entrypoint = (_DOCKER_DIR / "entrypoint-seat.sh").read_text(
        encoding="utf-8")
    # Coming up with an empty seat must fail here rather than downstream.
    assert "libinput list-devices" in entrypoint
    # Both layouts, as the capture image does: the negative-origin one is the
    # only one where the layout corner and layout (0, 0) differ.
    assert "-1280 0" in entrypoint

    script = (_DOCKER_DIR / "seat_verify.py").read_text(encoding="utf-8")
    # grim -c is what makes the cursor visible to a screenshot at all.
    assert '"-c"' in script
    # And the two findings the image exists to hold.
    assert "layout corner" in script
    assert "acceleration" in script


def test_seat_verification_job_grants_uinput_and_the_input_cgroup():
    raw = (_REPO_ROOT / ".github" / "workflows" / "docker.yml").read_text(
        encoding="utf-8",
    )
    assert "seat-verification" in raw
    assert "docker/Dockerfile.seat" in raw
    assert "autocontrol-seat:ci" in raw


def test_portal_verification_image_and_scripts_exist():
    """The portal path is only verified while these three files are wired up."""
    dockerfile = (_DOCKER_DIR / "Dockerfile.portal").read_text(encoding="utf-8")
    # liboeffis is a separate binary package that libei1 does not depend on,
    # so installing libei alone leaves the portal route quietly off.
    assert "liboeffis1" in dockerfile
    assert "portal_verify.py" in dockerfile
    assert "portal_server.py" in dockerfile
    # gdbus must stay out: the Screenshot tier speaks D-Bus itself now, and
    # this image is the proof that it needs no binary beyond a session bus.
    assert "libglib2.0-bin" not in dockerfile

    server = (_DOCKER_DIR / "portal_server.py").read_text(encoding="utf-8")
    # A portal that answers only CreateSession is not a portal; the fd handover
    # at the end of the dance is the whole point.
    for method in ("CreateSession", "SelectDevices", "Start", "ConnectToEIS"):
        assert method in server, f"mock portal missing {method}"
    assert "UnixFDList" in server, "the mock must really pass a descriptor"

    verify = (_DOCKER_DIR / "portal_verify.py").read_text(encoding="utf-8")
    # Refusals are half the value: a portal that says no must fail closed.
    for behaviour in ("deny", "stall", "no-fd", "close"):
        assert f'"{behaviour}"' in verify, f"no scenario drives {behaviour}"


def test_portal_verification_job_runs_the_image():
    raw = (_REPO_ROOT / ".github" / "workflows" / "docker.yml").read_text(
        encoding="utf-8",
    )
    assert "portal-verification" in raw
    assert "docker/Dockerfile.portal" in raw
    assert "autocontrol-portal:ci" in raw


def test_x11_verification_image_and_script_exist():
    """The X11 path is only verified while these three files are wired up."""
    dockerfile = (_DOCKER_DIR / "Dockerfile.x11").read_text(encoding="utf-8")
    # Each tool is ground truth from a different codebase than the subject:
    # xev reads events back out of a real client, `import` is an independent
    # grabber, xdotool/xdpyinfo are the server answering for itself.
    for tool in ("xvfb", "x11-utils", "xdotool", "imagemagick", "openbox"):
        assert tool in dockerfile, f"Dockerfile.x11 missing {tool}"
    assert "x11_verify.py" in dockerfile
    assert "entrypoint-x11.sh" in dockerfile

    verify = (_DOCKER_DIR / "x11_verify.py").read_text(encoding="utf-8")
    # XSendEvent traffic arrives with `synthetic YES` and is discarded by most
    # toolkits. Losing this assertion would let the backend quietly stop
    # driving real input while every other check still passed.
    assert "synthetic" in verify
    # The three readers have to be checked against each other, not just run.
    for reader in ("get_pixel", "screenshot", "truth_capture"):
        assert reader in verify, f"x11_verify.py never exercises {reader}"

    entrypoint = (_DOCKER_DIR / "entrypoint-x11.sh").read_text(encoding="utf-8")
    # A pass with no window manager tests nothing that reads _NET_*, and a
    # skipped second layout would silently drop the dual-monitor geometry.
    assert "openbox" in entrypoint
    assert "--setmonitor" in entrypoint


def test_x11_verification_refuses_to_skip_a_missing_layout():
    """A layout that cannot be declared is a failure, not a reason to skip.

    Every other verification job in docker/ fails loudly when its
    precondition is absent; a quiet skip reads as coverage that is not there.
    """
    entrypoint = (_DOCKER_DIR / "entrypoint-x11.sh").read_text(encoding="utf-8")
    assert "exit 1" in entrypoint
    assert "not a reason to skip" in entrypoint


def test_x11_verification_job_runs_the_image():
    raw = (_REPO_ROOT / ".github" / "workflows" / "docker.yml").read_text(
        encoding="utf-8",
    )
    assert "x11-verification" in raw
    assert "docker/Dockerfile.x11" in raw
    assert "autocontrol-x11:ci" in raw


def test_gitlab_template_covers_build_test_smoke_stages():
    raw = (_REPO_ROOT / "ci_templates" / ".gitlab-ci.yml").read_text(
        encoding="utf-8",
    )
    for stage in ("build", "test", "smoke"):
        assert stage in raw, f"gitlab template missing stage: {stage}"
    assert "docker:24-dind" in raw
    assert "pytest" in raw


def test_docs_run_in_ci_page_exists_and_covers_both_pipelines():
    raw = (_REPO_ROOT / "docs" / "source" / "getting_started" /
           "run_in_ci.rst").read_text(encoding="utf-8")
    for needle in ("GitHub Actions", "GitLab CI", "Kubernetes",
                    "Dockerfile.xfce", "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER"):
        assert needle in raw, f"docs page missing section: {needle}"
