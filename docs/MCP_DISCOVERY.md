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
The inspector also owns an isolated disclosure preview; real deployments use explicit settings.

Actual offscreen dialog frame and environment metadata are retained under
`benchmarks/results/mcp-discovery-g1`; no native device operation was performed.


## Session availability (Beta)

Full mode is the default, preserving the exact unpaged {tools: descriptors} shape
and registry order. JE_AUTOCONTROL_MCP_TOOL_MODE chooses full/progressive/static;
JE_AUTOCONTROL_MCP_TOOL_PROFILE is a comma-separated canonical-name static profile
(max100 names, validated on deployment); JE_AUTOCONTROL_MCP_TOOL_PAGE_SIZE is an
explicit integer1–100. MCPServer.configure_tool_disclosure applies the same settings
before clients connect. Core is probe/discover/schema/enable/disable/state when those
tools exist in that registry. Custom registries must include the factories explicitly.

Each progressive ToolView has its own selection. Enable validates the entire batch
against current identity/readonly before mutation, ignores duplicate/core enables,
and notifies once only on change. Disable can clear removed/revoked names and never
removes core availability. Selections are bounded to1000. Full/static views reject
changes. State filters currently authorized names and removed registry entries.
Availability never grants call/path/env privileges. AC_run_agent is unchanged.

Opaque nextCursor values authenticate snapshot/offset with a per-owner secret.
Snapshots preserve registry order, copied definitions and version across plugin
changes; schema export rechecks current permission. Each view retains at most8
snapshots for120sec; eviction/expiry/foreign signatures/changed permission fail
explicitly. A page also carries snapshotId/registryVersion; repeated cursors are
stable. Single-page replies retain no snapshot. Close revokes and clears all state.
Request ContextVar leases keep the accepted view even after its owner is dropped,
so late handlers see a closed view instead of creating a replacement owner.

HTTP SessionRegistry drop/eviction/shutdown closes views. Notifications resolve the
live standing stream by metadata lookup, without retaining transient POST writers.
Enable notifies only its owner; plugin changes refresh registered live HTTP owners
and retain the prior stdio/subscription notification path. Static advertises no
listChanged. Stateless MCP requests have no session mutation or continuation cursor:
full/static deployments use fixed availability; progressive falls back to core only.
These clients can choose a configured static profile. Full/default behavior remains.

preview_tool_disclosure returns every selected descriptor from an ephemeral owner,
without a continuation cursor or real session changes. Facade/AC/Builder preview
uses the local default registry; MCP preview uses its serving registry. GUI preview
retains its own view/cursor for mode selection, static comma-separated names,
enable/disable and next page. Apply replaces that owner; close/Escape revokes it.


### Policy and measured cost

Stdio flags `--tool-mode`, `--tool-profile` and `--tool-page-size` override corresponding
mode/profile/page-size settings; existing flags and full catalog inspection remain.
Readonly rejects mutating custom-registry calls as well as hiding/disallowing enable.
Availability never replaces the existing schema/RBAC/root/env/rate/confirmation checks.
Concurrent work captures accepted peer identity, roots and capabilities, including after
session removal; the original closed view lease cannot create a replacement session.
Controlled regressions verify root denial, authenticated audits and removed-tool rejection.
`benchmarks/mcp_discovery.py --output report.json` compares identical registry/policy
with one warmup/five samples and records source hash/platform/version. Reference:
full747/363544bytes, core6/2506bytes; local initialize+list37.91/9.56ms and
search9.78/9.65ms. This measures local JSON-RPC, excluding networking/native input.
Artifact: `benchmarks/results/mcp-discovery-g3/report.json`.
