"""Tests for the config bundle export / import (round 36)."""
import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from je_auto_control.utils.config_bundle import (
    BUNDLE_VERSION, ConfigBundleError, ConfigBundleExporter,
    export_config_bundle, import_config_bundle,
)
from je_auto_control.utils.rest_api.rest_server import RestApiServer


_TEST_SCHEME = "http"  # NOSONAR localhost-only ephemeral test server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_config_root(root: Path) -> None:
    """Lay down a representative selection of config files."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "admin_hosts.json").write_text(
        json.dumps({"hosts": [{"label": "lab-01"}]}),
        encoding="utf-8",
    )
    (root / "address_book.json").write_text(
        json.dumps({"entries": []}),
        encoding="utf-8",
    )
    (root / "remote_host_id").write_text("AC1234567", encoding="utf-8")
    # Intentionally no trusted_viewers.json so we exercise "missing"


# ---------------------------------------------------------------------------
# Exporter
# ---------------------------------------------------------------------------


def test_export_includes_present_files_only(tmp_path):
    _seed_config_root(tmp_path)
    bundle = ConfigBundleExporter(root=tmp_path).build()
    assert set(bundle["files"]) == {
        "admin_hosts.json", "address_book.json", "remote_host_id",
    }
    assert bundle["files"]["remote_host_id"]["format"] == "text"
    assert bundle["files"]["admin_hosts.json"]["format"] == "json"


def test_export_manifest_has_required_fields(tmp_path):
    _seed_config_root(tmp_path)
    bundle = export_config_bundle(root=tmp_path)
    manifest = bundle["manifest"]
    for key in ("version", "exported_at", "platform", "source_root"):
        assert key in manifest
    assert manifest["version"] == BUNDLE_VERSION


def test_export_skips_invalid_json_gracefully(tmp_path):
    """A corrupt JSON file should NOT crash the whole export."""
    _seed_config_root(tmp_path)
    (tmp_path / "trusted_viewers.json").write_text(
        "{not really json}", encoding="utf-8",
    )
    bundle = export_config_bundle(root=tmp_path)
    assert "trusted_viewers.json" not in bundle["files"]
    assert "admin_hosts.json" in bundle["files"]


def test_export_on_missing_root_returns_empty_files(tmp_path):
    bundle = export_config_bundle(root=tmp_path / "does-not-exist")
    assert bundle["files"] == {}


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------


def test_round_trip_writes_identical_files(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _seed_config_root(src)
    bundle = export_config_bundle(root=src)

    report = import_config_bundle(bundle, root=dst)
    assert set(report.written) == {
        "admin_hosts.json", "address_book.json", "remote_host_id",
    }
    assert (dst / "remote_host_id").read_text(encoding="utf-8") == "AC1234567"
    restored = json.loads((dst / "admin_hosts.json").read_text("utf-8"))
    assert restored == {"hosts": [{"label": "lab-01"}]}


def test_import_creates_backup_when_overwriting(tmp_path):
    _seed_config_root(tmp_path)
    bundle = export_config_bundle(root=tmp_path)
    # Now mutate the on-disk file before re-importing the original bundle.
    (tmp_path / "admin_hosts.json").write_text("{}", encoding="utf-8")
    report = import_config_bundle(bundle, root=tmp_path)
    assert "admin_hosts.json" in report.backups
    backup_name = report.backups["admin_hosts.json"]
    backup_path = tmp_path / backup_name
    assert backup_path.exists()
    assert backup_path.read_text(encoding="utf-8") == "{}"


def test_import_dry_run_does_not_write(tmp_path):
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    _seed_config_root(src)
    bundle = export_config_bundle(root=src)
    report = import_config_bundle(bundle, root=dst, dry_run=True)
    assert "admin_hosts.json" in report.written
    assert not (dst / "admin_hosts.json").exists()


def test_import_rejects_unknown_version(tmp_path):
    bundle = {
        "manifest": {"version": 99},
        "files": {},
    }
    with pytest.raises(ConfigBundleError) as exc_info:
        import_config_bundle(bundle, root=tmp_path)
    assert "version" in str(exc_info.value)


def test_import_rejects_missing_manifest(tmp_path):
    with pytest.raises(ConfigBundleError):
        import_config_bundle({"files": {}}, root=tmp_path)


def test_import_rejects_non_dict_payload(tmp_path):
    with pytest.raises(ConfigBundleError):
        import_config_bundle("hello", root=tmp_path)


def test_import_skips_unknown_filenames(tmp_path):
    bundle = {
        "manifest": {"version": 1, "exported_at": "now"},
        "files": {
            "admin_hosts.json": {"format": "json", "content": {"hosts": []}},
            "something_evil.txt": {"format": "text", "content": "boom"},
        },
    }
    report = import_config_bundle(bundle, root=tmp_path)
    assert "admin_hosts.json" in report.written
    assert "something_evil.txt" in report.skipped
    assert not (tmp_path / "something_evil.txt").exists()


def test_import_skips_path_traversal_attempts(tmp_path):
    bundle = {
        "manifest": {"version": 1, "exported_at": "now"},
        "files": {
            "../escape.json": {"format": "json", "content": {}},
        },
    }
    report = import_config_bundle(bundle, root=tmp_path)
    assert report.written == []
    assert "../escape.json" in report.skipped


def test_import_skips_format_mismatch(tmp_path):
    """Bundle claims text but allowlist says JSON → reject that entry."""
    bundle = {
        "manifest": {"version": 1, "exported_at": "now"},
        "files": {
            "admin_hosts.json": {"format": "text", "content": "plain"},
        },
    }
    report = import_config_bundle(bundle, root=tmp_path)
    assert report.written == []
    assert "admin_hosts.json" in report.skipped


# ---------------------------------------------------------------------------
# REST integration
# ---------------------------------------------------------------------------


@pytest.fixture()
def server():
    s = RestApiServer(host="127.0.0.1", port=0, enable_audit=False)
    s.start()
    yield s
    s.stop(timeout=1.0)


def _post(server, path, body, *, token=None):
    host, port = server.address
    url = f"{_TEST_SCHEME}://{host}:{port}{path}"
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=3) as response:  # nosec B310  # reason: localhost test server
        return response.status, json.loads(response.read().decode("utf-8"))


def test_rest_config_export_round_trips(server):
    status, body = _post(server, "/config/export", {}, token=server.token)
    assert status == 200
    assert "manifest" in body and "files" in body


def test_rest_config_export_requires_token(server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post(server, "/config/export", {})
    assert exc_info.value.code == 401


def test_rest_config_import_rejects_bad_bundle(server):
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post(server, "/config/import", {"oops": True}, token=server.token)
    assert exc_info.value.code == 400
    payload = json.loads(exc_info.value.read().decode("utf-8"))
    assert "rejected" in payload.get("error", "")
