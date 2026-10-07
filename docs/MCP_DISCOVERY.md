# MCP registry discovery (Beta)

The registry is the only definition source. ToolIndex snapshots copied descriptors
and the server mutation version under the registry lock. register/unregister (also
plugin watcher updates) advance the version. Existing indexes retain their original
definitions; a fresh server query sees the current registry. One ToolIndex never
executes a handler, probes a device or imports Qt.

Search validates query <=512 characters and integer limit1–100, excluding bools.
It searches names, full descriptions and factory categories case-insensitively;
all whitespace-separated terms must match. Name matches rank ahead of description
matches, then names sort deterministically. Replies contain name, description
<=240 characters, typed category, reviewed base required_capability and read_only;
no inputSchema/outputSchema. Factory names supply category metadata, aliases retain
the canonical category, plugin tools use plugin; custom tools default to general. Categories are metadata,
not permission decisions. Schema lookup validates a nonempty name <=256 characters
and returns exactly one copy-on-export MCPToolDescriptor. Unavailable and denied
names share ToolDiscoveryError (AutoControlException/ValueError).

Each query checks current RBAC, plus readonly and any explicitly supplied narrowing
predicate. A predicate can narrow access but cannot grant it. Required capability
comes from the server-owned catalog, never provider annotations; argument-specific
requirements can be stronger (such as screenshot writing). Schema access does not
grant execution, client roots or environment permissions. Existing call validation,
argument/path/env guards and dispatcher remain in force.

`discover_tools` and `get_tool_schema` / matching `AC_discover_tools` and
`AC_get_tool_schema` / Script Builder / Tools → MCP tool discovery inspect the
local default registry. MCP `ac_discover_tools` and `ac_get_tool_schema` instead
resolve ToolCallContext.tool_index from the actual serving server, including its
custom tools and plugin version. Search structuredContent is {version, tools};
schema structuredContent is the one MCP descriptor. A custom registry must include
the discovery factory explicitly to expose these tools; no hidden tools are added
to old custom registries. Full legacy tools/list behavior is preserved.

The GUI inspector is lazy, shows query/limit/name and readonly results, with
Actions for search, schema and cancel. It copies inputs before shared background
work; close revokes task delivery. It does not attach to or change a remote session.
Runtime session disclosure is tracked by G2 in Progress.md.

Actual offscreen dialog frame and environment metadata are retained under
`benchmarks/results/mcp-discovery-g1`; no native device operation was performed.
