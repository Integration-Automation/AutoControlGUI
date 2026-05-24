"""DAG runner: schedule nodes with parallel execution + skip cascade.

Local nodes go through the in-process executor; remote nodes go
through :class:`AdminConsoleClient`. Failures cascade — every node
whose ancestry contains a failure is marked ``skipped`` rather than
attempted, so a broken upstream doesn't trigger a thundering herd of
remote calls.
"""
from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Set

from je_auto_control.utils.dag.graph import (
    DagDefinition, DagDefinitionError, DagNode, parse_definition,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"

LOCAL_HOST = "local"


@dataclass
class NodeResult:
    """Outcome of one node execution."""

    id: str
    host: str
    status: str = STATUS_PENDING
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    duration_ms: float = 0.0
    result: Any = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if not isinstance(self.result, (str, int, float, bool, list,
                                          dict, type(None))):
            data["result"] = repr(self.result)
        return data


@dataclass
class DagRunResult:
    """Aggregate outcome of one DAG execution."""

    succeeded: bool
    elapsed_s: float
    nodes: Dict[str, NodeResult] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "succeeded": bool(self.succeeded),
            "elapsed_s": float(self.elapsed_s),
            "nodes": {nid: result.to_dict()
                      for nid, result in self.nodes.items()},
        }


# A NodeRunner is anything callable that accepts (node, definition)
# and returns the raw result of executing that node. Used to inject a
# fake executor in tests so we don't need a live REST host or a real
# screen.
NodeRunner = Callable[[DagNode, DagDefinition], Any]


def run_dag(definition: Any,
            *,
            max_parallel: int = 4,
            local_runner: Optional[NodeRunner] = None,
            remote_runner: Optional[NodeRunner] = None,
            ) -> DagRunResult:
    """Execute ``definition`` in topological order with bounded parallelism.

    ``definition`` may be a :class:`DagDefinition` or the JSON-shaped
    mapping :func:`parse_definition` accepts. ``local_runner`` /
    ``remote_runner`` let tests substitute the real dispatch with a
    pure-Python fake — both default to the production paths.
    """
    dag = _coerce_definition(definition)
    local = local_runner or _default_local_runner
    remote = remote_runner or _default_remote_runner
    started_at = time.monotonic()
    nodes_by_id = dag.by_id()
    results = {nid: NodeResult(id=nid, host=nodes_by_id[nid].host)
               for nid in nodes_by_id}
    _execute_with_pool(dag, results, local, remote, max(1, int(max_parallel)))
    elapsed = round(time.monotonic() - started_at, 3)
    succeeded = all(r.status == STATUS_SUCCEEDED for r in results.values())
    return DagRunResult(
        succeeded=succeeded, elapsed_s=elapsed, nodes=results,
    )


def _coerce_definition(definition: Any) -> DagDefinition:
    if isinstance(definition, DagDefinition):
        return definition
    if isinstance(definition, Mapping):
        return parse_definition(definition)
    raise DagDefinitionError(
        "definition must be a DagDefinition or a JSON mapping",
    )


def _execute_with_pool(dag: DagDefinition,
                       results: Dict[str, NodeResult],
                       local: NodeRunner, remote: NodeRunner,
                       max_parallel: int) -> None:
    """Schedule nodes whose deps are all done; cascade skip on failure."""
    pending: Set[str] = set(results)
    inflight: Dict[Future, str] = {}
    failed_ancestors: Dict[str, Set[str]] = _ancestor_index(dag)
    nodes_by_id = dag.by_id()
    failed: Set[str] = set()
    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        while pending or inflight:
            _spawn_ready_nodes(
                pending, inflight, results, failed,
                failed_ancestors, nodes_by_id, local, remote, pool,
            )
            if not inflight:
                continue
            _harvest_one(inflight, results, failed)


def _spawn_ready_nodes(pending: Set[str], inflight: Dict[Future, str],
                       results: Dict[str, NodeResult], failed: Set[str],
                       ancestors: Dict[str, Set[str]],
                       nodes_by_id: Dict[str, DagNode],
                       local: NodeRunner, remote: NodeRunner,
                       pool: ThreadPoolExecutor) -> None:
    for nid in sorted(pending):
        node = nodes_by_id[nid]
        deps_done = {results[d].status for d in node.depends_on}
        if {STATUS_PENDING, STATUS_RUNNING} & deps_done:
            continue
        if ancestors[nid] & failed:
            results[nid].status = STATUS_SKIPPED
            pending.discard(nid)
            continue
        results[nid].status = STATUS_RUNNING
        results[nid].started_at = time.monotonic()
        runner = local if node.host == LOCAL_HOST else remote
        future = pool.submit(_run_one, node, results[nid], runner, nodes_by_id)
        inflight[future] = nid
        pending.discard(nid)


def _harvest_one(inflight: Dict[Future, str],
                 results: Dict[str, NodeResult],
                 failed: Set[str]) -> None:
    finished = next(iter(inflight))
    nid = inflight.pop(finished)
    try:
        finished.result()
    except (RuntimeError, OSError, ValueError) as error:
        # Defensive: _run_one swallows tool errors into NodeResult.
        # This branch only catches pool / runner-side faults.
        results[nid].status = STATUS_FAILED
        results[nid].error = repr(error)
    if results[nid].status == STATUS_FAILED:
        failed.add(nid)


def _run_one(node: DagNode, result: NodeResult,
             runner: NodeRunner, _nodes: Dict[str, DagNode]) -> None:
    try:
        outcome = runner(node, _build_proxy_definition(node, _nodes))
    except (RuntimeError, OSError, ValueError) as error:
        result.status = STATUS_FAILED
        result.error = f"{type(error).__name__}: {error}"
        autocontrol_logger.warning(
            f"DAG node {node.id!r} failed: {result.error}",
        )
    else:
        result.status = STATUS_SUCCEEDED
        result.result = outcome
    finished_at = time.monotonic()
    result.finished_at = finished_at
    if result.started_at is not None:
        result.duration_ms = round(
            (finished_at - result.started_at) * 1000.0, 2,
        )


def _build_proxy_definition(node: DagNode,
                            nodes_by_id: Dict[str, DagNode]) -> DagDefinition:
    """Compact DagDefinition exposing just this node — runners rarely need
    more, but the signature is uniform so test runners can introspect
    upstream metadata if they want.
    """
    chain = {node.id: node}
    queue = list(node.depends_on)
    while queue:
        dep = queue.pop()
        if dep in chain:
            continue
        upstream = nodes_by_id.get(dep)
        if upstream is None:
            continue
        chain[dep] = upstream
        queue.extend(upstream.depends_on)
    return DagDefinition(nodes=tuple(chain.values()))


def _ancestor_index(dag: DagDefinition) -> Dict[str, Set[str]]:
    """Pre-compute the transitive ancestor set per node id."""
    parents: Dict[str, Set[str]] = {n.id: set(n.depends_on) for n in dag.nodes}
    ancestors: Dict[str, Set[str]] = {}
    for nid in dag.topological_order():
        own: Set[str] = set(parents[nid])
        for parent in list(parents[nid]):
            own.update(ancestors.get(parent, set()))
        ancestors[nid] = own
    return ancestors


def _default_local_runner(node: DagNode, _definition: DagDefinition) -> Any:
    from je_auto_control.utils.executor.action_executor import (
        execute_action, execute_files,
    )
    if node.actions is not None:
        return execute_action(list(node.actions))
    return execute_files([node.action_file])


def _default_remote_runner(node: DagNode,
                           _definition: DagDefinition) -> Any:
    from je_auto_control.utils.admin.admin_client import default_admin_console
    console = default_admin_console()
    actions = _resolve_remote_actions(node)
    rows = console.broadcast_execute(actions, labels=[node.host])
    if not rows:
        raise RuntimeError(
            f"no registered admin host with label {node.host!r}",
        )
    row = rows[0]
    if not row.get("ok"):
        raise RuntimeError(
            f"remote {node.host!r} failed: {row.get('error')}",
        )
    return row.get("result")


def _resolve_remote_actions(node: DagNode) -> List[Any]:
    if node.actions is not None:
        return list(node.actions)
    import json
    with open(node.action_file, "r", encoding="utf-8") as fp:
        loaded = json.load(fp)
    if not isinstance(loaded, list):
        raise RuntimeError(
            f"action_file {node.action_file!r} must contain a list",
        )
    return loaded


__all__ = [
    "DagRunResult", "LOCAL_HOST", "NodeResult", "NodeRunner",
    "STATUS_FAILED", "STATUS_PENDING", "STATUS_RUNNING",
    "STATUS_SKIPPED", "STATUS_SUCCEEDED", "run_dag",
]
