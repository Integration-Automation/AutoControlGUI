# Native input acknowledgement revalidation

Original P1/P2/P7 item10 requires human takeover and target identity to remain authoritative until
input dispatch. The actual current-worker synthetic probe in stage108/input-ack-boundary-probe01.json
shows activity or target invalidation during owner ACK does not prevent the observer returning to
the keyboard wrapper. The wrapper then calls its backend. No actual input was used in that probe.

Revalidate the same live activity gate and target after a valid owner ACK, before returning to any
input wrapper. Also check activity after mouse preparation, alongside the existing target check.
An invalid or missing ACK must still fail; require one ack field whose value is exactly boolean true,
rejecting numeric1/1.0, extra fields and malformed JSON. The change grants no retry or new deadline.
Keep the original pre-ACK checks and pointer preparation ordering.

Cleanup remains the private _release_owned path. It may release only previously announced owned
keys/buttons after takeover or target loss; its observer accepts key_release/key_released and
mouse_release/mouse_released events only. Cleanup never authorizes a press, pointer move, text or
scroll. Existing input ledger, journal and parent ACK validate actual ownership; the event-kind
restriction is additional containment, not ownership proof.

Put the reusable check in NativeWorker._validate_input(event:dict)->None and call it before sending
the event, after mouse preparation and after valid ACK. Reuse _check_activity; no new imports,
wire fields, API, dependency, version, persistence or source ownership are needed.

Tests exercise the actual worker and real input wrappers with only fake backend functions and
in-memory ACK streams. Assert backend calls are absent on invalidation, healthy ordering remains,
invalid ACK never authorizes input and cleanup actually releases owned input without new presses.
The existing pointer-order test gains the explicit final validation assertion.

All work is background. Native/real-browser/device/24hour acceptance remains deferred. This closes
the ACK boundary only; persistent Windows source/transport and the original40items remain open.
No shared installation, real input, deployment, paid feature or model download is authorized here.
