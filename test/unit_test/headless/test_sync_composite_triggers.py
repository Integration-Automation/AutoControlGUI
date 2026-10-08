"""Composite triggers sync as definitions, and still arrive disarmed.

``AllOfTrigger`` / ``AnyOfTrigger`` / ``SequenceTrigger`` hold other trigger
objects, so the trigger adapter left them on the machine they were made on
(listed under ``withheld``). "At 09:00 and only if the image is on screen" is
exactly the kind of trigger a person builds once and wants everywhere.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from je_auto_control.utils.config_sync import (
    ConfigSyncClient, ConfigSyncConflict, ConfigSyncError, SyncOutbox, TriggerSyncAdapter,
    run_sync,
)
from je_auto_control.utils.triggers.trigger_engine import (
    AllOfTrigger, AnyOfTrigger, CronTrigger, FilePathTrigger, ImageAppearsTrigger,
    PixelColorTrigger, SequenceTrigger, TriggerEngine, WindowAppearsTrigger,
)

_URL = "https://sync.invalid"


class _Server:
    def __init__(self):
        self.body = None
        self.revision = 0

    def request(self, method, body=None):
        if method == "GET":
            return self.body
        if body["base_revision"] != self.revision:
            raise ConfigSyncConflict("behind", self.revision)
        self.revision += 1
        self.body = {**body["bucket"], "revision": self.revision}
        return {"ok": True, "revision": self.revision}


@pytest.fixture
def server():
    endpoint = _Server()
    with patch.object(ConfigSyncClient, "_request",
                      new=lambda _client, method, body=None: endpoint.request(method, body)):
        yield endpoint


class _Machine:
    def __init__(self, tmp_path, name):
        self.name = name
        self.scripts = tmp_path / name / "scripts"
        self.scripts.mkdir(parents=True)
        self.ran = []
        self.engine = TriggerEngine(executor=self.ran.append)
        self.outbox = SyncOutbox(tmp_path / name / "outbox.sqlite3", account="alice",
                                 endpoint=_URL, base_delay_s=0.0)
        self.adapter = TriggerSyncAdapter(name, self.engine, scripts_dir=self.scripts)

    def sync(self):
        return run_sync(ConfigSyncClient(_URL, user_id="alice"), self.outbox, [self.adapter],
                        device_id=self.name)

    def triggers(self):
        return {trigger.trigger_id: trigger for trigger in self.engine.list_triggers()}


@pytest.fixture
def pair(tmp_path, server):
    return _Machine(tmp_path, "laptop"), _Machine(tmp_path, "desktop")


def _morning(laptop):
    return AllOfTrigger(
        trigger_id="morning", script_path=str(laptop.scripts / "report.json"), repeat=True,
        cooldown_seconds=30.0, enabled=True, children=[
            CronTrigger(trigger_id="at-nine", script_path="", cron="0 9 * * *"),
            ImageAppearsTrigger(trigger_id="logo", script_path="",
                                image_path=str(laptop.scripts / "logo.png"), threshold=0.9),
        ])


def test_an_all_of_trigger_reaches_the_other_machine_with_its_children(pair, server):
    laptop, desktop = pair
    laptop.engine.add(_morning(laptop))
    assert laptop.sync().withheld == {}
    report = desktop.sync()

    received = desktop.triggers()["morning"]
    assert isinstance(received, AllOfTrigger)
    assert (received.repeat, received.cooldown_seconds) == (True, 30.0)
    assert Path(received.script_path) == desktop.scripts / "report.json"
    cron, image = received.children
    assert isinstance(cron, CronTrigger) and cron.cron == "0 9 * * *"
    assert isinstance(image, ImageAppearsTrigger) and image.threshold == pytest.approx(0.9)
    # The child's path was made portable and resolved against this machine's folder.
    assert Path(image.image_path) == desktop.scripts / "logo.png"
    assert [child.trigger_id for child in received.children] == ["at-nine", "logo"]
    assert report.applied["triggers"]["left_disabled"] == ["morning"]
    json.dumps(server.body)


def test_a_composite_arrives_disabled_and_nothing_runs(pair):
    laptop, desktop = pair
    laptop.engine.add(_morning(laptop))
    laptop.sync()
    desktop.sync()
    received = desktop.triggers()["morning"]
    assert received.enabled is False
    assert all(child.enabled is False for child in received.children)
    assert desktop.ran == [] and laptop.ran == []
    # ... and it stays disabled when the definition is updated later.
    laptop.triggers()["morning"].cooldown_seconds = 60.0
    laptop.sync()
    desktop.sync()
    again = desktop.triggers()["morning"]
    assert again.cooldown_seconds == pytest.approx(60.0) and again.enabled is False


def test_a_composite_this_machine_enabled_stays_enabled_across_an_update(pair):
    laptop, desktop = pair
    laptop.engine.add(_morning(laptop))
    laptop.sync()
    desktop.sync()
    desktop.engine.set_enabled("morning", True)          # this machine's own choice
    laptop.triggers()["morning"].repeat = False
    laptop.sync()
    desktop.sync()
    assert desktop.triggers()["morning"].enabled is True
    assert desktop.triggers()["morning"].repeat is False


def test_any_of_sequence_and_nesting_round_trip(pair, server):
    laptop, desktop = pair
    inner = AnyOfTrigger(trigger_id="either", script_path="", children=[
        WindowAppearsTrigger(trigger_id="win", script_path="", title_substring="Report"),
        PixelColorTrigger(trigger_id="px", script_path="", x=3, y=4, target_rgb=(1, 2, 3))])
    laptop.engine.add(SequenceTrigger(
        trigger_id="steps", script_path=str(laptop.scripts / "a.json"), children=[
            FilePathTrigger(trigger_id="file", script_path="",
                            watch_path=str(laptop.scripts / "in.csv")),
            inner]))
    laptop.sync()
    desktop.sync()
    steps = desktop.triggers()["steps"]
    assert isinstance(steps, SequenceTrigger)
    watched, either = steps.children
    assert Path(watched.watch_path) == desktop.scripts / "in.csv"
    assert isinstance(either, AnyOfTrigger)
    assert either.children[1].target_rgb == (1, 2, 3)
    assert either.children[0].title_substring == "Report"
    # Unchanged on both sides: nothing more is sent.
    before = server.revision
    assert laptop.sync().pending == 0 and desktop.sync().pending == 0
    assert server.revision == before


def test_editing_a_child_is_a_change_and_deleting_the_composite_propagates(pair, server):
    laptop, desktop = pair
    laptop.engine.add(_morning(laptop))
    laptop.sync()
    desktop.sync()
    laptop.triggers()["morning"].children[0] = CronTrigger(
        trigger_id="at-nine", script_path="", cron="30 8 * * *")
    laptop.sync()
    desktop.sync()
    assert desktop.triggers()["morning"].children[0].cron == "30 8 * * *"
    laptop.engine.remove("morning")
    laptop.sync()
    desktop.sync()
    assert "morning" not in desktop.triggers()


def test_a_child_that_is_not_a_known_trigger_keeps_the_composite_local(pair, server):
    laptop, _desktop = pair

    class _Custom:
        def is_fired(self):
            return False

    laptop.engine.add(AnyOfTrigger(trigger_id="odd", script_path="", children=[_Custom()]))
    report = laptop.sync()
    assert "_Custom" in report.withheld["triggers/odd"]
    assert server.body is None or "odd" not in server.body["sections"].get("triggers", {})


def test_the_registering_principal_is_never_sent(pair, server):
    laptop, _desktop = pair
    trigger = _morning(laptop)
    laptop.engine.add(trigger)
    trigger.owner = object()                 # stands for an RBAC principal
    trigger.children[0].owner = object()
    laptop.sync()
    assert "owner" not in json.dumps(server.body)


@pytest.mark.parametrize("children", [
    "not-a-list", [{"type": "NoSuchTrigger"}], [7],
    [{"type": "CronTrigger", "cron": "not a cron"}],
])
def test_a_malformed_composite_is_skipped_not_half_built(tmp_path, children):
    engine = TriggerEngine(executor=lambda _actions: None)
    adapter = TriggerSyncAdapter("desktop", engine, scripts_dir=tmp_path)
    with pytest.raises((ConfigSyncError, ValueError, TypeError)):
        adapter.write_local("bad", {"type": "AllOfTrigger", "script_path": "", "children": children},
                            None)
    assert engine.list_triggers() == []


def test_nesting_and_width_are_bounded(tmp_path):
    engine = TriggerEngine(executor=lambda _actions: None)
    adapter = TriggerSyncAdapter("desktop", engine, scripts_dir=tmp_path)
    deep = {"type": "CronTrigger", "trigger_id": "leaf", "cron": "* * * * *"}
    for level in range(12):
        deep = {"type": "AllOfTrigger", "trigger_id": f"l{level}", "children": [deep]}
    with pytest.raises(ConfigSyncError, match="nested"):
        adapter.write_local("deep", {**deep, "script_path": ""}, None)
    wide = [{"type": "CronTrigger", "trigger_id": f"c{index}", "cron": "* * * * *"}
            for index in range(500)]
    with pytest.raises(ConfigSyncError, match="children"):
        adapter.write_local("wide", {"type": "AnyOfTrigger", "script_path": "", "children": wide},
                            None)
    assert engine.list_triggers() == []
