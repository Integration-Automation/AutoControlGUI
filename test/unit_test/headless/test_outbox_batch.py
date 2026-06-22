"""Headless tests for the transactional outbox. No Qt."""
import je_auto_control as ac
from je_auto_control.utils.outbox import Outbox


def test_enqueue_marks_pending():
    box = Outbox()
    first = box.enqueue({"type": "a"})
    box.enqueue({"type": "b"})
    assert first == "1"
    assert [e["event"]["type"] for e in box.pending()] == ["a", "b"]


def test_drain_delivers_all():
    box = Outbox()
    box.enqueue({"n": 1})
    box.enqueue({"n": 2})
    seen = []
    result = box.drain(seen.append)
    assert result == {"sent": 2, "failed": 0, "remaining": 0}
    assert [e["n"] for e in seen] == [1, 2]
    assert box.pending() == []


def test_drain_retries_then_dead_letters():
    box = Outbox()
    box.enqueue({"n": 1})

    def always_fail(_event):
        raise RuntimeError("sink down")

    # Below max_attempts: stays pending for retry.
    for _ in range(4):
        box.drain(always_fail, max_attempts=5)
    assert len(box.pending()) == 1
    assert box.dead_letters() == []
    # Fifth attempt exhausts and dead-letters.
    box.drain(always_fail, max_attempts=5)
    assert box.pending() == []
    dead = box.dead_letters()
    assert len(dead) == 1 and dead[0]["error"] == "sink down"


def test_drain_resumes_after_transient_failure():
    box = Outbox()
    box.enqueue({"n": 1})
    calls = {"count": 0}

    def flaky(_event):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("blip")

    box.drain(flaky)             # fails, stays pending
    result = box.drain(flaky)    # succeeds now
    assert result["sent"] == 1
    assert box.pending() == []


def test_max_batch_limits_delivery():
    box = Outbox()
    for i in range(5):
        box.enqueue({"n": i})
    sent = []
    result = box.drain(sent.append, max_batch=2)
    assert result == {"sent": 2, "failed": 0, "remaining": 3}


def test_save_load_round_trip(tmp_path):
    box = Outbox()
    box.enqueue({"n": 1})
    path = str(tmp_path / "outbox.json")
    box.save(path)
    restored = Outbox.load(path)
    assert len(restored.pending()) == 1
    assert restored.enqueue({"n": 2}) == "2"   # counter preserved


# --- wiring ---------------------------------------------------------------

def test_executor_round_trip():
    name = "outbox-exec-test"
    rec = ac.execute_action([[
        "AC_outbox_enqueue", {"name": name, "event": '{"type": "x"}'}]])
    out = next(v for v in rec.values() if isinstance(v, dict))
    assert out["id"] == "1" and out["pending"] == 1
    rec2 = ac.execute_action([["AC_outbox_pending", {"name": name}]])
    pending = next(v for v in rec2.values() if isinstance(v, dict))["pending"]
    assert pending[0]["event"]["type"] == "x"


def test_wiring():
    known = ac.executor.known_commands()
    assert {"AC_outbox_enqueue", "AC_outbox_pending"} <= set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_outbox_enqueue", "ac_outbox_pending"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_outbox_enqueue", "AC_outbox_pending"} <= specs


def test_facade_exports():
    assert hasattr(ac, "Outbox") and "Outbox" in ac.__all__
