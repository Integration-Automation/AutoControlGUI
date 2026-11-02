"""Workspace lease, binding and resync-baseline tables belong to the owned outbox transaction."""

WORKSPACE_TABLES = (
    'CREATE TABLE sync_workspace_leases (endpoint TEXT NOT NULL,user_id TEXT NOT NULL,owner TEXT NOT NULL,'
    'lease_until REAL NOT NULL,last_attempt REAL NOT NULL,error_code TEXT NOT NULL DEFAULT \'\','
    'PRIMARY KEY(endpoint,user_id))',
    'CREATE TABLE sync_workspace_bindings (endpoint TEXT NOT NULL,user_id TEXT NOT NULL,kind TEXT NOT NULL,'
    'binding TEXT NOT NULL,PRIMARY KEY(endpoint,user_id,kind))',
    'CREATE TABLE sync_workspace_baselines (endpoint TEXT NOT NULL,user_id TEXT NOT NULL,operation_id TEXT NOT NULL,'
    'kind TEXT NOT NULL,configuration TEXT NOT NULL,wire TEXT NOT NULL,digest TEXT NOT NULL,'
    'PRIMARY KEY(endpoint,user_id,operation_id,kind))',
)
