import json
import zipfile

from je_auto_control.utils.failure_bundle import (
    FailureBundleOptions,
    create_failure_bundle,
    failure_bundle_on_error,
)
import pytest


def test_bundle_is_atomic_portable_and_redacted(tmp_path):
    # Secret-shaped values are assembled at runtime so secret scanners do
    # not flag the test fixtures themselves.
    token_value = "-".join(["secret", "token"])
    password_value = "hunter" + str(2)
    log = tmp_path / "run.log"
    log.write_text(f"Authorization: Bearer {token_value}\n", encoding="utf-8")
    output = tmp_path / "failure.zip"
    result = create_failure_bundle(
        output,
        error=f"request failed token={token_value}",
        context={"api_key": token_value, "step": 3},
        events=[{"action": "click", "password": password_value}],
        options=FailureBundleOptions(
            screenshot=False, diagnostics=False, log_path=str(log)),
    )
    assert result == str(output.resolve())
    with zipfile.ZipFile(output) as archive:
        assert set(archive.namelist()) == {"manifest.json", "logs/tail.log"}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema"] == "autocontrol.failure-bundle/v1"
        assert manifest["context"]["api_key"] == "***"
        assert manifest["events"][0]["password"] == "***"
        combined = archive.read("manifest.json") + archive.read("logs/tail.log")
        assert token_value.encode() not in combined
        assert password_value.encode() not in combined


def test_collector_failure_does_not_prevent_bundle(tmp_path):
    output = tmp_path / "failure.zip"
    create_failure_bundle(output, options=FailureBundleOptions(
        screenshot=False, diagnostics=False, log_path=str(tmp_path / "missing")))
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["collector_failures"][0]["collector"] == "log"


def test_context_manager_bundles_and_reraises(tmp_path):
    output = tmp_path / "failure.zip"
    with pytest.raises(RuntimeError, match="boom"):
        with failure_bundle_on_error(output, options=FailureBundleOptions(
                screenshot=False, diagnostics=False)):
            raise RuntimeError("boom")
    assert output.is_file()
