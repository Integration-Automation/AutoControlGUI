"""Archive completion rechecks output files independently of the original tool receipt."""
import hashlib
import json

import pytest

from je_auto_control.utils.agent_runtime import AgentTaskSpec
from je_auto_control.utils.agent_runtime.policy import TaskPolicy
from je_auto_control.utils.agent_runtime.verification import verify, validate_criteria


@pytest.fixture
def archive(tmp_path):
    path = tmp_path / "report.txt"
    path.write_bytes(b"saved")
    entry = {"name": path.name, "path": str(path), "bytes": 5, "sha256": hashlib.sha256(b"saved").hexdigest()}
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": [entry]}), encoding="utf-8")
    clause = {"kind": "file_manifest", "path": str(manifest), "directory": str(tmp_path), "names": [path.name]}
    policy = TaskPolicy(AgentTaskSpec.from_dict({"goal": "archive", "roots": [str(tmp_path)],
        "allowed_tools": ["AC_workflow_manifest"], "success_criteria": [clause]}))
    return policy, path, manifest


def test_current_matching_archive_is_independent_completion_evidence(archive):
    policy, _path, _manifest = archive
    assert verify(policy, [], {}) == [{"kind": "file_manifest", "status": "passed"}]


def test_modified_file_cannot_reuse_a_previous_successful_manifest(archive):
    policy, path, _manifest = archive
    path.write_bytes(b"other")
    assert verify(policy, [], {}) == [{"kind": "file_manifest", "status": "failed"}]


def test_manifest_cannot_redirect_evidence_to_an_unreviewed_file(archive, tmp_path):
    policy, _path, manifest = archive
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["files"][0]["path"] = str(tmp_path / "unreviewed.txt")
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert verify(policy, [], {}) == [{"kind": "file_manifest", "status": "failed"}]


@pytest.mark.parametrize("names", [[], ["a", "a"], [False]])
def test_invalid_manifest_contract_is_rejected(names):
    with pytest.raises(ValueError):
        validate_criteria([{"kind": "file_manifest", "directory": "/root", "path": "/root/m.json", "names": names}])
