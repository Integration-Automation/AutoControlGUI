"""Explicit journal recording and validated read tools."""
from typing import List

from je_auto_control.utils.action_journal.api import execute_journaled, list_journal_runs, read_action_journal
from je_auto_control.utils.mcp_server.tools._base import DESTRUCTIVE, MCPTool, READ_ONLY, schema


def journal_tools() -> List[MCPTool]:
    """Expose version-one journals without executing read/conversion inputs."""
    text = {'type': 'string'}
    return [
        MCPTool(name='ac_execute_journaled', description='Execute an action list and persist sanitized step events.',
                input_schema=schema({'actions': {'type': ['array', 'object', 'string']}, 'path': text, 'run_id': text,
                                     'raise_on_error': {'type': 'boolean'}, 'device': text, 'session': text},
                                    required=['actions', 'path']),
                handler=execute_journaled, annotations=DESTRUCTIVE),
        MCPTool(name='ac_read_action_journal', description='Read validated steps, optionally selected by run ID.',
                input_schema=schema({'path': text, 'run_id': text}, required=['path']),
                handler=read_action_journal, annotations=READ_ONLY),
        MCPTool(name='ac_list_journal_runs', description='List recorded runs with statuses and step counts.',
                input_schema=schema({'path': text}, required=['path']),
                handler=list_journal_runs, annotations=READ_ONLY),
    ]
