"""Phase 4.1: RFC 6238 TOTP tests."""
import pytest

from je_auto_control.utils.remote_desktop.totp import (
    TOTPError, generate_code, generate_secret, provisioning_uri,
    verify_code,
)


# RFC 6238 SHA-1 test vector: secret ``12345678901234567890`` (ASCII)
# corresponds to base32 ``GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ`` and yields
# the code ``94287082`` at Unix time 59 with 8-digit output.
# NOSONAR python:S6418  # reason: published RFC 6238 reference test vector
_RFC_SECRET_B32 = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # nosec B105  # reason: RFC test vector


def test_rfc6238_known_vector_8_digit():
    code = generate_code(_RFC_SECRET_B32, at=59.0, digits=8)
    assert code == "94287082"


def test_rfc6238_known_vector_at_step_boundary():
    # t=1111111109 → just before step boundary, expect 07081804
    code = generate_code(_RFC_SECRET_B32, at=1111111109, digits=8)
    assert code == "07081804"


def test_generated_code_is_six_digits_by_default():
    secret = generate_secret()
    code = generate_code(secret)
    assert len(code) == 6 and code.isdigit()


def test_verify_accepts_current_code():
    secret = generate_secret()
    now = 1700000000.0
    code = generate_code(secret, at=now)
    assert verify_code(secret, code, at=now) is True


def test_verify_tolerates_one_step_drift():
    secret = generate_secret()
    now = 1700000000.0
    code = generate_code(secret, at=now)
    # Same code 25 s later should still pass within the default ±1 window.
    assert verify_code(secret, code, at=now + 25) is True


def test_verify_rejects_distant_code():
    secret = generate_secret()
    now = 1700000000.0
    code = generate_code(secret, at=now)
    # Past the ±1 window (default 30s steps → 90s away is window=3).
    assert verify_code(secret, code, at=now + 200) is False


def test_verify_rejects_wrong_code():
    secret = generate_secret()
    assert verify_code(secret, "000000") is False or \
        verify_code(secret, "999999") is False


def test_verify_rejects_malformed_input():
    secret = generate_secret()
    assert verify_code(secret, "abcdef") is False
    assert verify_code(secret, "12345") is False  # too short
    assert verify_code(secret, 123456) is False  # type: ignore[arg-type]  # NOSONAR python:S5655  # reason: intentional bad-type negative test


def test_decode_secret_handles_spaces_and_lowercase():
    # The Google Authenticator UI shows secrets in spaced lowercase.
    # Sanity-check: ours should accept that format.
    spaced = "GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ"
    lower = spaced.lower()
    code1 = generate_code(spaced, at=59.0, digits=8)
    code2 = generate_code(lower, at=59.0, digits=8)
    assert code1 == "94287082"
    assert code2 == "94287082"


def test_invalid_secret_raises():
    with pytest.raises(TOTPError):
        generate_code("not-base32!!!")
    with pytest.raises(TOTPError):
        generate_code("")


def test_provisioning_uri_contains_secret_and_issuer():
    secret = "GEZDGNBVGY3TQOJQ"  # nosec B105  # NOSONAR python:S6418  # reason: published RFC 6238 test vector, not a real credential
    uri = provisioning_uri(secret, account="alice", issuer="MyApp")
    assert uri.startswith("otpauth://totp/")
    assert "secret=GEZDGNBVGY3TQOJQ" in uri
    assert "issuer=MyApp" in uri
    assert "MyApp%3Aalice" in uri  # URL-encoded "MyApp:alice"


def test_generate_secret_random():
    a = generate_secret()
    b = generate_secret()
    assert a != b
    assert len(a) >= 16  # base32 expansion of 20-byte secret


# --- end-to-end host/viewer integration ----------------------------------

def test_host_with_totp_admits_correct_code():
    from io import BytesIO
    from PIL import Image
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
    from je_auto_control.utils.remote_desktop.viewer import (
        RemoteDesktopViewer,
    )

    def jpeg():
        img = Image.new("RGB", (8, 8), color=(0, 0, 0))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()

    secret = generate_secret()
    host = RemoteDesktopHost(
        token="abc", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=jpeg, totp_secret=secret,
    )
    host.start()
    try:
        # Right code: connects.
        good_code = generate_code(secret)
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="abc",
            totp_code=good_code,
        )
        viewer.connect(timeout=5.0)
        try:
            assert viewer.connected
        finally:
            viewer.disconnect(timeout=1.0)
    finally:
        host.stop(timeout=1.0)


def test_host_with_totp_rejects_wrong_code():
    from io import BytesIO
    from PIL import Image
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
    from je_auto_control.utils.remote_desktop.viewer import (
        RemoteDesktopViewer,
    )
    from je_auto_control.utils.remote_desktop.protocol import (
        AuthenticationError,
    )

    def jpeg():
        img = Image.new("RGB", (8, 8), color=(0, 0, 0))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()

    secret = generate_secret()
    host = RemoteDesktopHost(
        token="abc", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=jpeg, totp_secret=secret,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="abc",
            totp_code="000000",
        )
        with pytest.raises((AuthenticationError, OSError, ConnectionError)):
            viewer.connect(timeout=3.0)
    finally:
        host.stop(timeout=1.0)


def test_host_with_totp_rejects_token_alone():
    """A viewer that knows only the token but not the TOTP must fail."""
    from io import BytesIO
    from PIL import Image
    from je_auto_control.utils.remote_desktop.host import RemoteDesktopHost
    from je_auto_control.utils.remote_desktop.viewer import (
        RemoteDesktopViewer,
    )
    from je_auto_control.utils.remote_desktop.protocol import (
        AuthenticationError,
    )

    def jpeg():
        img = Image.new("RGB", (8, 8), color=(0, 0, 0))
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()

    secret = generate_secret()
    host = RemoteDesktopHost(
        token="abc", bind="127.0.0.1", port=0, fps=30.0,
        frame_provider=jpeg, totp_secret=secret,
    )
    host.start()
    try:
        viewer = RemoteDesktopViewer(
            host="127.0.0.1", port=host.port, token="abc",
        )
        with pytest.raises((AuthenticationError, OSError, ConnectionError)):
            viewer.connect(timeout=3.0)
    finally:
        host.stop(timeout=1.0)
