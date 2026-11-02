"""Durable receipt review, provenance and retention use fake effects and private test caches."""
import base64
import io
import json
import time

import pytest

from je_auto_control.utils.agent_runtime import AgentRuntime, AgentTaskError
from je_auto_control.utils.agent_runtime.runner import run_task
from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope


class Counter:
    def __init__(self):
        self.value = 0
        self.fail = False
        self.image = None

    def ready(self, _spec):
        return True, ""

    def observe(self):
        data = {"identity": "fixture", "value": self.value}
        if self.image is not None:
            data["image"] = self.image
        return data

    def perform(self, _tool, _arguments):
        if self.fail:
            raise AgentTaskError("unknown effect")
        self.value += 1
        return {"value": self.value}

    def cleanup(self):
        pass


@pytest.fixture
def runtime(tmp_path):
    target = Counter()
    instance = AgentRuntime(tmp_path / "runtime.sqlite", targets={"fixture": target})
    yield instance, target
    instance.close()


def spec(**changes):
    return {"goal": "count", "target": "fixture", "allowed_tools": ["AC_increment"],
            "success_criteria": [{"kind": "result_equals", "key": "value", "value": 1}], **changes}


def act(runtime, task_id):
    frame = runtime.observe(task_id)
    return runtime.act(task_id, {"tool": "AC_increment", "observation_id": frame.observation_id})


def test_task_links_private_history_journal_and_report(runtime):
    from pathlib import Path
    instance, _target = runtime
    task = instance.submit(spec())
    act(instance, task.task_id)
    result = instance.finish(task.task_id)
    metadata = result.to_dict()["metadata"]
    events = [json.loads(line) for line in Path(metadata["journal_path"]).read_text(encoding="utf-8").splitlines()]
    assert [event["status"] for event in events] == ["incomplete", "ok"]
    assert all(event["run_id"] == task.task_id for event in events)
    history = instance.evidence.history.list_runs()
    assert history[0].status == "ok"
    assert instance.evidence.history.journals_for_run(metadata["history_id"])[0].journal_run_id == task.task_id
    report = json.loads(Path(history[0].artifact_path).read_text(encoding="utf-8"))
    assert report["state"] == "succeeded"
    assert report["actions"][0]["status"] == "confirmed"


def test_owner_review_does_not_resume_or_replay_an_uncertain_effect(runtime):
    instance, target = runtime
    target.fail = True
    task = instance.submit(spec())
    with pytest.raises(AgentTaskError):
        act(instance, task.task_id)
    with pytest.raises(AgentTaskError, match="uncertain"):
        instance.resume(task.task_id)
    receipt = instance.receipts(task.task_id)["actions"][0]
    instance.reconcile(task.task_id, {"action_id": receipt["id"], "decision": "applied",
                                     "note": "Operator read the saved value independently", "result": {"value": 1}})
    assert instance.get(task.task_id).state == "waiting_user"
    assert instance.receipts(task.task_id)["reviews"][0]["actor"] == "local"
    instance.resume(task.task_id)
    assert instance.finish(task.task_id).state == "succeeded"
    assert target.value == 0


def test_reviewed_non_effect_can_retry_without_consuming_the_next_skill_step(runtime):
    instance, target = runtime
    task = instance.submit(spec(mode="skill", actions=[{"tool": "AC_increment", "expect_result": {"value": 1}}],
                                success_criteria=[{"kind": "actions_complete"}]))
    target.fail = True
    assert run_task(instance, task.task_id).state == "waiting_user"
    receipt = instance.receipts(task.task_id)["actions"][0]
    instance.reconcile(task.task_id, {"action_id": receipt["id"], "decision": "not_applied",
                                     "note": "Operator confirmed no record was created"})
    target.fail = False
    instance.resume(task.task_id)
    assert run_task(instance, task.task_id).state == "succeeded"
    assert target.value == 1
    assert [item["status"] for item in instance.receipts(task.task_id)["actions"]] == ["not_applied", "confirmed"]
    assert instance.get(task.task_id).steps == 2


def test_cancelled_unknown_effect_can_be_reviewed_without_reopening_the_task(runtime):
    instance, target = runtime
    target.fail = True
    task = instance.submit(spec())
    with pytest.raises(AgentTaskError):
        act(instance, task.task_id)
    receipt = instance.receipts(task.task_id)["actions"][0]
    instance.cancel(task.task_id)
    result = instance.reconcile(task.task_id, {"action_id": receipt["id"], "decision": "not_applied",
                                              "note": "Reviewed after cancellation"})
    assert result.state == "cancelled"
    with pytest.raises(AgentTaskError, match="not ready"):
        instance.resume(task.task_id)


def test_committed_receipt_cannot_be_silently_rewritten(runtime):
    instance, _target = runtime
    task = instance.submit(spec())
    receipt = act(instance, task.task_id)
    with pytest.raises(AgentTaskError, match="committed"):
        instance.store.settle(receipt.action_id, "uncertain")


def test_missing_journal_before_dispatch_has_no_effect_and_allows_explicit_retry(runtime, monkeypatch):
    instance, target = runtime
    task = instance.submit(spec())
    original = instance.evidence.action
    monkeypatch.setattr(instance.evidence, "action", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError, match="disk"):
        act(instance, task.task_id)
    assert target.value == 0
    assert instance.receipts(task.task_id)["actions"][0]["status"] == "failed"
    monkeypatch.setattr(instance.evidence, "action", original)
    instance.resume(task.task_id)
    act(instance, task.task_id)
    assert instance.finish(task.task_id).state == "succeeded"


def test_images_are_ephemeral_until_explicit_strict_redaction_opt_in(runtime):
    instance, target = runtime
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "black").save(buffer, format="JPEG")
    target.image = {"format": "jpeg", "redacted_by": "strict", "data": base64.b64encode(buffer.getvalue()).decode()}
    first = instance.submit(spec())
    instance.observe(first.task_id)
    assert not list(instance.evidence.directory(first.task_id).glob("*.jpg"))
    instance.pause(first.task_id)
    second = instance.submit(spec(options={"persist_images": True}))
    instance.observe(second.task_id)
    assert len(list(instance.evidence.directory(second.task_id).glob("*.jpg"))) == 1


def expire(instance, task_id):
    instance.cancel(task_id)
    with instance.store.connection(write=True) as connection:
        connection.execute("UPDATE agent_tasks SET updated=? WHERE id=?", (time.time() - 31 * 86400, task_id))


def test_retention_preserves_user_outputs_and_external_journals(runtime, tmp_path):
    instance, _target = runtime
    task = instance.submit(spec())
    output, external = tmp_path / "output.txt", tmp_path / "external.jsonl"
    output.write_text("user output", encoding="utf-8")
    external.write_text("external journal", encoding="utf-8")
    link = instance.evidence.metadata(task.task_id)
    instance.evidence.history.attach_journal(link["history_id"], str(external), "external")
    expire(instance, task.task_id)
    assert instance.prune()["deleted"] == [task.task_id]
    assert not instance.evidence.directory(task.task_id).exists()
    assert output.read_text(encoding="utf-8") == "user output"
    assert external.read_text(encoding="utf-8") == "external journal"
    assert instance.evidence.history.list_runs() == []
    with pytest.raises(AgentTaskError):
        instance.get(task.task_id)


def test_retention_is_owner_scoped(runtime):
    instance, _target = runtime
    with authorization_scope(AuthorizationContext("alice", "operator")):
        first = instance.submit(spec())
        expire(instance, first.task_id)
    with authorization_scope(AuthorizationContext("bob", "operator")):
        second = instance.submit(spec())
        expire(instance, second.task_id)
        assert instance.prune()["deleted"] == [second.task_id]
    assert instance.get(first.task_id).state == "cancelled"


def test_retention_refuses_unrecognized_cache_files(runtime):
    instance, _target = runtime
    task = instance.submit(spec())
    unknown = instance.evidence.directory(task.task_id) / "do-not-delete.txt"
    unknown.write_text("foreign content", encoding="utf-8")
    expire(instance, task.task_id)
    with pytest.raises(AgentTaskError, match="unrecognized"):
        instance.prune()
    assert unknown.exists()
