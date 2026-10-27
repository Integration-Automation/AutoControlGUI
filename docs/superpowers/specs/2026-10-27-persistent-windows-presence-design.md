# Persistent Windows physical presence

Original P1/P2/P7 item10 requires one continuing human-activity source per interactive Windows
session across tasks, profiles, databases and input-helper generations. Existing per-helper hooks
and GetLastInputInfo cannot provide that contract. Keep original40items and native deferrals open.

## Authority and time

A fresh source waits60seconds from verified monitoring start, using its own monotonic clock only.
It requires an unlocked/default input desktop and no held input for acquisition. Source loss, stale
samples older than0.25seconds, invalid/regressing clock or invalid native data refuse permission.
An observation gap resets physical idle and fences old revisions; a fresh healthy sample must then
observe a new60seconds. Invalid clocks/native failures permanently retire that source instance.
Physical input and lock/unlock transitions advance a revision; a lease binds one revision and source
generation. A failed lease never rearms. Running leases may retain their own held input; held state
alone gates new acquisition. At most16leases exist; explicit release retires only its own presence
token and never certifies that keyboard/mouse input has been released. Native input locks/journals
remain authoritative for input ownership and cleanup. Generation/lease IDs are random32lowerhex.

Only header presence is retained, never key values, text, coordinates or input contents. Inspection
returns coarse availability/idle/held/interactive/revision/generation with native_evidence=not_recorded.
It does not install a driver. New observer import/construction/status/file/browser work introduces
no DLL load or monitoring resource. Existing package platform DLL bindings remain unchanged.

## Native observer

Run a fixed bundled observer in a dedicated hidden helper. Raw Input registration is per-process
one-window-per-class; do not register from the GUI/runtime. Create an HWND_MESSAGE window, no visible
window/focus, and register mouse(usagepage1,usage2), keyboard(1,6), all digitizers(0x0d,0,page-only),
using RIDEV_INPUTSINK without suppressing legacy input. Read RID_HEADER only. A zero device handle
may be a precision touchpad and is treated conservatively as physical presence, never discarded.
Ignore ordinary key/mouse/character messages as authority. Raw Input's direct-device semantics are
not a documented GetCurrentInputMessageSource guarantee. Real injected/physical/touch/pen coverage
remains explicitly unverified until native acceptance is resumed.

Every fresh query drains the observer queue and verifies its actual registrations before reading
interactive/held state. Poll at50ms; at most1024messages per poll. Backlog refuses that sample and
continues draining, never authorizes from stale data. Invalid header/wait/registration/cleanup fails
closed. Unregister only owned classes still pointing at the owned window; destroy/unregister only
owned resources. Retain callback references until native window/class retirement is confirmed.

## Shared transport and lifecycle

A lazy same-process reference-counted PresencePool owns one fixed private broker via OwnedChannel.
The broker starts or borrows the per-session source. Source/reader named-pipe APIs run only inside
owned helpers, with current-user/System DACL, first-instance ownership and remote-client rejection.
Verify connected peer user/session/process liveness from actual OS handles, never supplied PIDs.
Source ownership stays with its launching broker; borrowers never stop it. Owner loss fences all
leases; replacement uses a fresh generation and a new60second observation period.

Only bounded UTF-8 JSON byte frames, no pickle:4096bytes/16clients. Protocol1 requests have exact
request_id/operation/body fields; replies echo request_id and a closed result/error projection.
Operations inspect/acquire/check/release; check/release accept exact generation/lease_id fields.
Reject duplicate/unknown fields, nonfinite data, bool-as-number and stale/wrong generations.

Each connection starts request_id at integer1 and accepts only the next value, at most2**63-1,
excluding bool. Reply fields are exactly request_id/status/result; status is ok/busy/lease_lost/
source_lost, with result=null on non-ok. Successful results have the exact existing source snapshot,
acquire generation/lease_id or release {released:true} shape. Validate replies before trusting them.
Expected busy/locked/revoked outcomes remain normal broker results: throwing inside OwnedChannel
would destroy the persistent source on each failed early acquisition. Fatal transport/deadline/native
source loss still retires the actual owned helper tree.

The fixed broker's owner bootstrap body is empty. Its internally created SourceProcess uses an
actual nested OwnedChannel/NativeJob and sends one private source bootstrap only after containment;
the source reserves first-instance ownership before constructing/starting an observer. Its optional
namespace is a trusted-code test seam on the child-owner protocol, never accepted on the broker's
task-facing bootstrap. The default is the actual current SID/session endpoint. Only native
ERROR_FILE_NOT_FOUND permits source creation; busy, access-denied or unknown connection failures do
not mean absent. A first-instance loser closes its own child and borrows the authenticated winner.
Busy initial inspection keeps the existing source/connection, just as early busy acquisition does.
At most16connection workers exist; a bounded admission queue transfers each slot to its worker's
cleanup. Each worker checks retained-peer liveness before dispatch and reply. Disconnect during
acquire still revokes a token minted before that worker observes the disconnect; it never stops a
different runtime's source. Source loss cannot implicitly relaunch/replay an existing binding.

One protocol instance owns one connection's issued tokens. Other connections may check an explicitly
received host lease capability but cannot release it. Disconnect permanently revokes only issued
presence tokens, including when the observation queue is blocked. WindowsPresenceSource.status()
provides passive classification only; .release(generation,lease_id) directly removes a token through
the state mutex without native calls, queues or keyboard/mouse cleanup. Neither can authorize input.

Handshake frames use protocol1, random32lowerhex challenges, native process creation time1..2**64-1
and source generation. Server sends protocol/challenge/birth/generation after opening the actual peer
process handle. Client verifies native peer user/session, then sends protocol/server_challenge/
challenge/birth with a fresh challenge. Server verifies the echo/client birth and live peer, then
replies protocol/challenge/birth/generation echoing the client's challenge. Client verifies echo,
birth/generation and actual peer-handle liveness. A buffered pre-challenge reply cannot prove a live
connection to a reused PID. No supplied PID selects process operations. The native pipe client uses
identification-only security QoS; current-user/System DACL and remote rejection remain mandatory.

Input helpers use one private I/O thread per live reader. Every check/watch has a0.25second outer
deadline; a blocked read/write invalidates the gate and emits the existing physical_input notice.
Its thread cannot be reused or retried; the parent retires the owned input-helper process. Broker
RPCs retain original action/15second bootstrap/3second retirement bounds through OwnedChannel.
No potentially unbounded pipe call runs directly in the runtime process. Prove blocked read/write/
accept retirement independently. This chooses owned-process fencing instead of assuming stdlib pipe
waits are bounded; earlier draft's native-event proposal is not required.

Actual Job active-process count0 alone may precede process-object termination signals. Retirement
also retains query/synchronize handles to native-enumerated members, verifies their actual Job
membership and waits for their process objects to signal. Job-empty checks, member enumeration,
process-object waits and launcher reaping share the original3second bound. An exhausted bound still
issues termination only through the owned Job; unknown/failed retirement retains ownership and cannot
claim retired. Never terminate a process by a PID from a frame or a process-list value.

Host TaskOperation supplies a lazy presence provider, never model/task JSON authority. Default desktop
workers require the host binding; no GetLastInputInfo fallback. They check the same lease before
and after ACK. File/browser/custom reviewed extensions do not start native monitoring. Task cleanup
retires its reader/input helper but retains the runtime source reference. Runtime.close retires all
input before closing presence references; serialize first bind/close races under existing ownership.
Unknown input journals remain fenced even with healthy presence. Preserve runtime.py750lines.

## Delivery

Implement actual Win32 driver and lifecycle, not fake-only providers. TDD exact59/60seconds, clocks,
lock/held/health/queue/source changes, cleanup ownership, two runtimes/databases, borrower/owner loss
and blocked IPC. Patch native APIs in tests; do not install hooks, create real windows or inject input.
Maintain750/75/7/10/4/120limits, no new cycles/duplicates/suppressions, dependencies/version/fees,
shared environment/model downloads, retries/replay, WAL/durability/deadline relaxation or deployment.
Compare and record actual versions/dependencies/source/artifact hashes before any owned isolated install.
Finish full source coverage, strict docs/shared surfaces and fresh compared artifacts before Windows
feature delivery. Deferred native/browser/device/24hour acceptance remains separate and unproven.

Primary sources:
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerrawinputdevices
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-rawinputdevice
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-rawinputheader
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getrawinputdata
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-msgwaitformultipleobjectsex
- https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-createnamedpipew
- https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew
- https://learn.microsoft.com/en-us/windows/desktop/api/winbase/nf-winbase-getnamedpipeserverprocessid
- https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights
- https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject
- https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject
- https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-terminateprocess
