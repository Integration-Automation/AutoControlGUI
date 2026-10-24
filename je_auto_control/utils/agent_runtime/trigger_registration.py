"""Insert normal and explicitly renewed trigger templates through one bounded transaction contract."""
from __future__ import annotations

import json
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import AgentTaskSpec
from je_auto_control.utils.agent_runtime.policy import durable_payload
from je_auto_control.utils.agent_runtime.trigger_config import next_due


def insert_registration(connection: Any, identifier: str, value: dict, spec: AgentTaskSpec,
                        config: dict, owner: dict, now: float) -> None:
    """Persist a reviewed binding enabled for future notifications, never a schedule backlog."""
    if connection.execute("SELECT COUNT(*) FROM agent_triggers").fetchone()[0] >= 200:
        raise AgentTaskError("a runtime supports at most two hundred configured task triggers")
    connection.execute("INSERT INTO agent_triggers VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (identifier, value.get("name", spec.goal), value["kind"], json.dumps(durable_payload(spec.to_dict())),
         json.dumps(owner), json.dumps(config), 1, next_due(value["kind"], config, now),
         value.get("last_event", ""), value.get("max_pending", 1), "", now))
