"""Cross-host DAG orchestrator.

Nodes carry ``(host, actions | action_file, depends_on)``. Local nodes
execute in-process; remote nodes go through the admin console's REST
broadcast path. Failures cascade — every node whose ancestry contains
a failure is reported as ``skipped`` rather than attempted.

Public surface::

    from je_auto_control import (
        DagDefinition, DagNode, DagRunResult,
        parse_dag, run_dag,
    )
"""
from je_auto_control.utils.dag.graph import (
    DagDefinition, DagDefinitionError, DagNode, parse_definition as parse_dag,
)
from je_auto_control.utils.dag.runner import (
    DagRunResult, LOCAL_HOST, NodeResult, NodeRunner,
    STATUS_FAILED, STATUS_PENDING, STATUS_RUNNING,
    STATUS_SKIPPED, STATUS_SUCCEEDED, run_dag,
)


__all__ = [
    "DagDefinition", "DagDefinitionError", "DagNode",
    "DagRunResult", "LOCAL_HOST", "NodeResult", "NodeRunner",
    "STATUS_FAILED", "STATUS_PENDING", "STATUS_RUNNING",
    "STATUS_SKIPPED", "STATUS_SUCCEEDED",
    "parse_dag", "run_dag",
]
