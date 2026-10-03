"""Protected definition synchronization and hash-checked asset tools."""
from typing import List

from je_auto_control.utils.config_sync.wire_api import (
    config_sync_apply, config_sync_exchange, config_sync_preview, config_sync_retry, config_sync_status,
    config_sync_assets,
)
from je_auto_control.utils.mcp_server.tools._base import DESTRUCTIVE, MCPTool, MCPToolAnnotations, schema


def config_sync_tools() -> List[MCPTool]:
    """Expose explicit operations; all read or write durable private sync state."""
    text = {'type': 'string'}
    connection = {'workspace_path': text, 'server_url': text, 'user_id': text}
    secret = {'shared_secret': {'type': 'string', 'writeOnly': True}}
    update = MCPToolAnnotations(destructive=False, idempotent=False)
    return [
        MCPTool('ac_config_sync_preview', 'Preview portable causal definitions; retain conflicts without applying.',
                schema({'definitions_path': text, **connection, **secret},
                       required=['definitions_path', *connection]), config_sync_preview, update),
        MCPTool('ac_config_sync_exchange', 'Publish protected definitions; local apply remains explicit.',
                schema({'definitions_path': text, **connection, **secret},
                       required=['definitions_path', *connection]), config_sync_exchange, update),
        MCPTool('ac_config_sync_apply', 'Apply a reviewed preview; keep triggers inactive.',
                schema({'definitions_path': text, 'preview_path': text, 'state_path': text, 'device_id': text,
                        'choices': {'type': ['object', 'string']}},
                       required=['definitions_path', 'preview_path', 'state_path', 'device_id']),
                config_sync_apply, DESTRUCTIVE),
        MCPTool('ac_config_sync_retry', 'Retry exact durable envelopes with bounded attempts.',
                schema({**connection, **secret}, required=list(connection)), config_sync_retry, update),
        MCPTool('ac_config_sync_status', 'Inspect local pending/revision state without network access.',
                schema(connection, required=list(connection)), config_sync_status, update),
        MCPTool('ac_config_sync_assets', 'Publish each complete asset after size/SHA256 verification.',
                schema({'manifest_path': text, 'source_root': text, 'destination_root': text},
                       required=['manifest_path', 'source_root', 'destination_root']), config_sync_assets, DESTRUCTIVE),
    ]
