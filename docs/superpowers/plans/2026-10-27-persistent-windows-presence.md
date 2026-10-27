# Persistent Windows physical presence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline; existing question opt-out applies. No per-stage agents. Final review is at the whole original P0-P9 goal's actual end.

**Goal:** Preserve trustworthy physical idle/takeover across tasks, runtimes and native-helper generations.

**Architecture:** A presence-only native observer owns revision-bound state in one session source.
Private brokers/readers carry closed byte frames under owned-process deadlines. A lazy runtime pool
shares the source independently of per-task input, with no model-selectable authority or fallback.

**Tech Stack:** Existing Python/ctypes/threading/queues/Win32/named pipes/OwnedChannel/NativeJob.

**Spec:** docs/superpowers/specs/2026-10-27-persistent-windows-presence-design.md

## Global Constraints

Background only; no native hooks/window/input/browser/device/24hour acceptance in this work.
No new dependency/version/shared installation/deployment/fees/model downloads. Original40items active.
Limits750file/75function/7parameters including self/CC10/nesting4/120columns; runtime.py750.
60seconds fresh physical idle, sample age<=0.25seconds, poll50ms/1024messages,16leases/clients,4096byte frames.
Original action/15second bootstrap/3second cleanup bounds remain; no retry/replay/WAL/durability relaxation.

## Review Focus

- A new source cannot import old idle time; replacement invalidates old generation/leases.
- Raw zero-device touchpad events still stop a lease; never read input payloads.
- Registration replacement/queue backlog/clock failure cannot be mistaken for healthy quiet input.
- Borrower close cannot terminate the source; owner loss cannot leave another runtime's lease usable.
- Runtime first-bind/close and late IPC replies cannot acquire authority after input/source retirement.

### Task 1: Physical state and actual isolated Win32 observer

**Files:** Create je_auto_control/utils/agent_runtime/presence_state.py, presence_win32.py,
presence_windows.py; tests test_agent_presence_state.py, test_agent_presence_win32.py,
test_agent_presence_windows.py. Update measured map/Progress/monthly for a coherent partial checkpoint.

**Interfaces:**
- PresenceState(clock:Callable=time.monotonic): refresh(interactive:bool,held:bool), physical(), fail(),
  inspect()->dict, acquire()->dict[generation,lease_id], check(generation:str,lease_id:str)->dict,
  release(generation:str,lease_id:str), close(). Constructor does not call clock/native APIs.
- Win32PresenceAPI(libraries:tuple|None=None,interactive:Callable=_interactive): open(physical:Callable),
  poll(timeout:float)->tuple[bool,bool],
  registrations()->set[tuple], close(). Actual ctypes implementation; trusted fake libraries only in tests.
- WindowsPresenceSource(api_factory:Callable|None=None,clock:Callable=time.monotonic): start(),
  request(operation:str,body:dict,timeout:float=0.25)->dict, close(). API lives on one owned observer
  thread; fresh poll precedes each queued request; bounded16request queue and finite shutdown.

- [x] RED exact59/60, stale/invalid/regressing clocks, lock/unlock, held-only acquisition, repeated
  takeover, no rearm, wrong/released IDs/generations,16lease cap/concurrency and no contents retained.
- [x] Implement the state core and verify focused GREEN; random32hex generation/lease IDs, no old clocks.
- [x] RED actual Win32 API calls against fake DLLs: HWND_MESSAGE/INPUTSINK/PAGEONLY, RID_HEADER only,
  zero device, legacy messages ignored, invalid header/wait/registration, bounded backlog and owned cleanup.
- [x] Implement real ctypes structures/signatures/resources; no WinDLL/resource start on import/construction.
- [x] RED/GREEN source actor: start/stop/error/timeout/overload, fresh query after physical callback,
  idle continuity, stale queue replies and close/start races; fake APIs only, no native execution.
- [x] Run these tests and existing activity/ACK/native lifecycle tests; measure structure/map/static,
  preserve known lint debt and original58 import contract, then record/commit/push the finite checkpoint.
  It does not mark original item10, transport, runtime wiring or native acceptance complete.

### Task 2: Session source, secure byte pipes and bounded private brokers

**Files:** Create presence_frames.py/presence_protocol.py, presence_security_windows.py,
presence_handshake.py/presence_pipe_windows.py, presence_worker.py/presence_broker.py. Modify presence_windows.py only
to share closed body validation and add passive status/direct negative-only presence release.
Extract the existing resource-free native layout views to presence_native_types.py and retain
presence_win32.py's private alias/ABI; the security layer must not depend on an observer implementation.
Tests test_agent_presence_protocol.py / test_agent_presence_handshake.py / test_agent_presence_pipe.py /
test_agent_presence_transport.py and existing source tests. Correct native_job.py/native_channel.py's
actual owned-tree retirement when real peer-process checks expose launcher-only retirement; cover it
with test_agent_native_job.py under the same original3second bound, without PID-selected termination.

**Interfaces:** PresenceProtocol(source:WindowsPresenceSource).request(value:dict)->dict implements
exact protocol1 request_id/operation/body. PresencePipe.connect()->connection and .listen()->listener
derive the endpoint from actual user SID/session, create first-instance secured pipes, validate OS
peer/session and expose send_bytes/recv_bytes(maxlength4096)/close only. Source worker serves16clients
and releases only each disconnected connection's presence tokens. Broker stdin/stdout follows existing
OwnedChannel envelopes: bootstrap, inspect, acquire, check, release. Launch source only after parent
has established its NativeJob. Source/borrower ownership is internal, never selected by task arguments.

Refined interfaces before code: encode_frame(dict)->bytes/decode_frame(bytes)->dict enforce4096bytes,
unique JSON keys/finite values; presence_body(str,dict)->dict shares existing source request validation.
validate_request(dict)->tuple[int,str,dict] and validate_response(dict,str,int,str)->dict require exact
sequence/status/result shapes in the spec. PresenceProtocol.request consumes sequential IDs, tracks
issued tokens, and .close revokes only those tokens via source.release; source.status is passive and
never substitutes for a fresh check. Ordinary busy/lease_lost broker results cannot raise inside
OwnedChannel.request. Handshake challenge/birth/source-generation fields are fixed in the spec.

- [x] RED closed frames/duplicates/oversize/nonfinite/wrong generations, no pickle or forwarded PID authority.
- [ ] RED secured native pipe factory with fake APIs and actual independent owned fake-source IPC:
  two brokers share generation, borrower close survives, owner loss refuses, replacement waits fresh60.
- [ ] Implement actual Windows pipe DACL/first-instance/remote-reject and peer/user/session checks;
  only owned helpers call blocking byte APIs, outer original deadlines/retirement bound every operation.
- [ ] Test blocked read/write/accept, half handshakes, capacity/late responses and loss during acquire;
  preserve source ownership and unknown input journals, no automatic second source or retries.
- [ ] Verify static/native-free regression and coherent records/publication; keep runtime wiring open.

Task2 partial checkpoint: stage111 protocol/source RED54failed19passed5deselected6.83s,
GREEN79passed8.51s includes an actual owned helper surviving expected busy and retaining its source
generation. Native process/security RED15failed3.08s, GREEN15passed3.03s: fake peer/process cases and
an actual query-only current-process/descriptor check, no observer/window/input. Final18modules
333passed85.85s/0skips0warnings/3327inputs unchanged. This is not the pipe/listener/server/broker
implementation: the remaining four Task2 checks and all Tasks3-4 stay open. No task-done2 claim.

### Task 3: Runtime pool, host binding and live reader gate

**Files:** Create presence_pool.py/presence_reader.py; modify context.py/native_target.py/native_worker.py,
runtime.py/runtime_lock.py only for minimal lazy lifetime wiring; existing target/capability diagnostics.
Tests test_agent_presence_pool.py / test_agent_presence_reader.py / test_agent_presence_runtime.py.

**Interfaces:** PresencePool.reference()->reference, reference.acquire(check,timeout)->dict and close();
same-process references share one owned broker. Host TaskOperation gains optional presence provider.
PresenceReader(binding:dict,takeover:Callable).ready()/check()/close() implement the existing activity
gate interface, one private I/O thread and0.25second bounded watch. Default desktop workers require
actual source binding; no local idle fallback. All blocking I/O remains in the owned input helper.

- [ ] RED two real runtimes/databases and task/helper replacement retain source generation/idle;
  inert file/browser/status paths and borrower close never start/stop another runtime's source.
- [ ] Implement lazy shared ownership, reader fresh checks before/after ACK and physical_input notices.
  Preserve input lock/journal/owned-release gates independently of presence health.
- [ ] RED/GREEN first-bind/close, owner/reader loss, stale replies, revoked/old lease, blocked watch,
  native cleanup failure and explicit resume; retired readers never rearm or continue new input.
- [ ] Expose coarse passive states with native_evidence=not_recorded; verify existing shared API/GUI/
  trigger lifetimes and non-Windows refusal. Keep runtime.py750 and original action deadlines.

### Task 4: Complete Windows feature verification and delivery

**Files:** README3/Sphinx2/architecture/map/AGENT_TASKS/API_LIFECYCLE/CAPABILITY_MATRIX/Progress/monthly.

- [ ] Run complete task/native/ownership/trigger/GUI/recovery/retention/reader regressions, original58
  exact import/SCC and full current Pylint normalized audit; whole Ruff/typing/Bandit/Radon/structure.
- [ ] Freeze actual inputs; full configured coverage in an absent owned C basetemp, inspect all skips/
  warnings/errors/atexit and raw hashes. Latest ACK source must be covered; preserve historical failures.
- [ ] Strict bilingual docs and exact fresh source/wheel/sdist/installed worker proof; record actual
  versions/deps/artifact hashes/target differences before any new owned isolated installation.
- [ ] Use actual monthly ID lock, Agent-only main mirror, explicit path commit/push/remote SHA/clean
  proof and actual task-done gates. Native/browser/device/24hour evidence stays deferred; original
  other platforms/devices/workflows/model/cross-host/full-goal requirements remain open.

Task1 checkpoint evidence: stage110 RED/GREEN logs, final72source cases15.14s and actual
native95813 TERMINAL0 expanded16modules264passed112.42s;3321inputs unchanged. Whole static/
original58 lint/import audits and41doc/structure tests passed their no-new-issue contracts.
New files satisfy structural budgets without exemptions; runtime.py stays750. A coherent
12path feature commit and actual task-done1 verifier bind these bytes. Tasks2-4, full latest
coverage/artifacts, native acceptance and original40items remain open. No runtime wiring
or current installed-artifact success is claimed from this partial component checkpoint.

Task2 second partial checkpoint: stage112 actual secured pipe/challenge components, owned-member retirement proof,22modules393passed145.08s,0skip0warning; all actual raw failures retained.
Actual source server/broker, shared-source ownership and runtime reader wiring remain absent.
Only the first Task2 checkbox is formally complete; no task-done2 or full Windows/goal completion.
