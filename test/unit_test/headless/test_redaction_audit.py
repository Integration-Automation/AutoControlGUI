"""Regression tests for the secret-detection and failure-bundle defects of the 2026-09-23 audit.

Key matching was a substring search (``tokenizer`` was a secret, ``apiKey``
in a nested list was not), numbers under a secret key and tuple members were
never checked, and free text kept ``db_password=``, Basic credentials and
``user:pass@`` URLs. The failure bundle wrote ``AC_secret_*`` arguments in
plain text, replaced the block's error with its own, and kept a half line at
the start of a truncated log. Screenshot redaction ignored ``x/y/width/height``
boxes and raised on palette, grayscale and bilevel images.
"""
import json
import zipfile

import pytest

from je_auto_control.utils.config_redaction import redact_config, redact_secret_text
from je_auto_control.utils.failure_bundle.bundle import (
    FailureBundleOptions, create_failure_bundle, failure_bundle_on_error,
)
from je_auto_control.utils.redaction.rules import _normalise_bbox
from je_auto_control.utils.secrets_scan import scan_secrets
from je_auto_control.utils.secrets_scan import secrets_scan as scan_module

_NO_COLLECTORS = FailureBundleOptions(screenshot=False, diagnostics=False)


@pytest.mark.parametrize("key", ["password", "db_password", "apiKey", "client-secret",
                                 "AWS_ACCESS_KEY", "sessionId", "Authorization"])
def test_secret_key_names_are_recognised(key):
    assert scan_module.is_secret_key(key)


@pytest.mark.parametrize("key", ["tokenizer", "bypass_proxy", "compass_heading", "passenger"])
def test_words_that_only_contain_a_secret_word_are_not_secrets(key):
    assert not scan_module.is_secret_key(key)


def test_list_items_and_numbers_under_a_secret_key_are_found():
    kinds = {finding["path"] for finding in scan_secrets(
        {"tokens": ["abc", "def"], "pin": {"password": 1234}, "db": ("admin", "s3cr3t-value")})}
    assert {"$.tokens[0]", "$.tokens[1]", "$.pin.password"} <= kinds


# Assembled at run time so secret scanners reading this file do not flag the
# fixtures themselves.
_PGP_HEADER = "-----BEGIN PGP PRIVATE " + "KEY BLOCK-----"
_JWT = ".".join(["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxIn0", "c2ln"])


@pytest.mark.parametrize("value, kind", [
    ("https://admin:hunter2@db.example.com/x", "url-credentials"),
    (_PGP_HEADER, "private-key-block"),
    ("bearer abcdefghijklmnopqrstuv", "bearer-token"),
    (_JWT, "jwt"),
])
def test_value_shapes_are_found(value, kind):
    assert [finding["kind"] for finding in scan_secrets({"note": value})] == [kind]


def test_a_redacted_config_keeps_its_tuple_members_masked():
    assert redact_config({"credentials": ("admin", "hunter2")}) == {"credentials": ["***", "***"]}


@pytest.mark.parametrize("text, secret", [
    ("connect db_password=hunter2 now", "hunter2"),
    ('{"client_secret": "abc123"}', "abc123"),
    ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
    ("GET https://admin:hunter2@db.example.com/x", "hunter2"),
])
def test_free_text_secrets_are_masked(text, secret):
    assert secret not in redact_secret_text(text)


def test_a_credentials_url_keeps_its_host():
    assert redact_secret_text("https://admin:hunter2@db.example.com/x") == \
        "https://admin:***@db.example.com/x"


def _manifest(path):
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("manifest.json"))


def test_vault_command_arguments_do_not_reach_the_bundle(tmp_path):
    bundle = create_failure_bundle(
        tmp_path / "b.zip", error="boom", options=_NO_COLLECTORS,
        events=[{"action": ["AC_secret_set", "db", "hunter2"]}],
        context={"actions": [["AC_secret_unlock", {"passphrase": "open-sesame"}]]})
    text = json.dumps(_manifest(bundle))
    assert "hunter2" not in text and "open-sesame" not in text


def test_the_blocks_error_survives_a_bundle_that_cannot_be_written(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(KeyError, match="original"):
        with failure_bundle_on_error(blocker / "sub" / "b.zip", options=_NO_COLLECTORS):
            raise KeyError("original")


def test_a_truncated_log_tail_drops_its_partial_first_line(tmp_path):
    log = tmp_path / "run.log"
    log.write_bytes(b"x" * 50 + b" password=hunter2\nsecond line\n")
    options = FailureBundleOptions(screenshot=False, diagnostics=False,
                                   log_path=str(log), log_tail_bytes=20)
    with zipfile.ZipFile(create_failure_bundle(tmp_path / "b.zip", options=options)) as archive:
        assert archive.read("logs/tail.log").decode("utf-8") == "second line\n"


@pytest.mark.parametrize("bbox, expected", [
    ({"x": 10, "y": 20, "width": 30, "height": 5}, (10, 20, 40, 25)),
    ({"left": 1, "top": 2, "right": 3, "bottom": 4}, (1, 2, 3, 4)),
    ([5, 6, 1, 2], (1, 2, 5, 6)),
])
def test_bounding_box_shapes(bbox, expected):
    assert _normalise_bbox(bbox) == expected


def test_a_bounding_box_without_coordinates_is_refused():
    with pytest.raises(ValueError, match="no coordinates"):
        _normalise_bbox({"w": 3})


@pytest.mark.parametrize("mode", ["P", "L", "1", "LA"])
@pytest.mark.parametrize("overlay", [None, (0, 0, 0)])
def test_redaction_handles_non_rgb_images(mode, overlay):
    image_module = pytest.importorskip("PIL.Image")
    from je_auto_control.utils.redaction.engine import _apply_blur
    source = image_module.new(mode, (20, 20), 1)
    out = _apply_blur(source, [(0, 0, 10, 10)], 3, overlay)
    assert out.size == (20, 20) and out.mode in ("RGB", "RGBA")
