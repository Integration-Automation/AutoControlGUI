=========================================================
USB Passthrough — Phase 2e Security Review Checklist
=========================================================

This page is for an external reviewer to walk before USB passthrough
is enabled by default. It is **not** itself a sign-off — that lives
in whatever ticket / record system the project uses.

Until every item below is checked off and signed by a reviewer who is
not the author of the code, the passthrough feature must remain
behind ``enable_usb_passthrough(True)`` (off by default).

.. contents::
   :local:
   :depth: 2


Threat model
============

Trust boundary: the **viewer** is a peer outside the host's local
trust domain. They can send arbitrary frames over the ``usb``
DataChannel. The host must never:

- Claim a device the operator has not approved (ACL).
- Claim more devices than the policy allows (max_claims).
- Spend unbounded buffer space on viewer-driven payloads (payload cap
  + credit window).
- Continue to honor a viewer that is provably misbehaving (rate / lockout,
  inherited from the REST auth gate when channels are gated by the
  same session).

The viewer is *also* a potential victim of a malicious host — but
this checklist is host-side only. A separate review for the viewer
client comes in Phase 2f.


ACL
===

- [ ] ``UsbAcl`` defaults to ``"deny"`` when no file exists. Verify
      with a fresh user account.
- [ ] When the file is corrupt / wrong version, the ACL also defaults
      to deny (test ``test_unknown_version_is_ignored``).
- [ ] ``prompt_on_open`` rules without a wired callback fall back to
      deny (test ``test_session_prompt_no_callback_means_deny``).
- [ ] If the prompt callback raises, the open is denied (test
      ``test_session_prompt_callback_raising_means_deny``).
- [ ] ACL file is written with mode ``0o600`` on POSIX (test
      ``test_save_persists_to_disk_with_safe_mode``).
- [ ] Recommend storing the ACL on a filesystem that supports POSIX
      permissions; document the Windows ACL story in the deploy guide.
- [ ] **OPEN question 8 — ACL integrity (HMAC / keychain)**. Currently
      a process running as the user can rewrite the ACL silently. If
      that's not acceptable, file the follow-up project before sign-off.


Audit
=====

- [ ] Every ACL decision is logged via ``audit_log`` with one of:
      ``usb_open_allowed``, ``usb_open_denied``,
      ``usb_open_rejected_max_claims``, ``usb_open_backend_error``,
      ``usb_close``. Confirm by inspecting recent audit rows after
      a manual exercise.
- [ ] Audit rows include ``viewer_id`` so a row can be attributed to
      a peer (test ``test_session_audit_captures_open_decisions``).
- [ ] Audit log itself is hash-chained (round 25). Confirm
      ``verify_chain()`` returns ``ok=True`` after a passthrough
      session.
- [ ] Frame-level transfer logging is intentionally OFF to avoid
      capturing key material on YubiKey-class devices. ERRORs only
      are surfaced via the project logger.


Protocol hardening
==================

- [ ] Frame header is 4 bytes; ``decode_frame`` rejects buffers
      smaller than that (test ``test_decode_rejects_short_buffer``).
- [ ] Unknown opcodes raise ``ProtocolError`` (test
      ``test_decode_rejects_unknown_opcode``) — the session never
      sees the bad frame.
- [ ] Payloads are capped at ``MAX_PAYLOAD_BYTES`` (16 KiB) on both
      decode (test ``test_decode_rejects_oversize_payload``) and
      construct (test ``test_frame_constructor_validates``).
- [ ] CTRL/BULK/INT request bodies that fail to parse return ERROR,
      not crash (test ``test_bad_transfer_payload_returns_error``).
- [ ] Backend exceptions are caught and returned as
      ``{"ok": false, "error": "..."}`` — the session never propagates
      a host-side RuntimeError to the wire (test
      ``test_backend_error_translates_to_ok_false``).


Resource bounds
===============

- [ ] ``max_claims`` cap enforced (test
      ``test_max_concurrent_claims_enforced``).
- [ ] CREDIT-based inbound flow control prevents a peer from filling
      the host's process queue (test ``test_credit_exhaustion_returns_error``).
- [ ] CREDIT replenishment is 1 frame per reply — well-behaved peer
      doesn't stall (test
      ``test_each_transfer_consumes_then_replenishes_one_credit``).
- [ ] CREDIT messages with bad payloads are silently dropped (test
      ``test_credit_message_with_bad_payload_is_ignored``).
- [ ] CREDIT for unknown claim_id is silent (test
      ``test_credit_message_for_unknown_claim_is_silent``).


Lifecycle
=========

- [ ] ``close_all()`` releases every outstanding handle and tolerates
      per-handle close errors (test
      ``test_close_all_releases_every_outstanding_claim``).
- [ ] FakeHandle ``close`` is idempotent (test
      ``test_backend_handle_close_is_idempotent``); same property
      verified for the libusb backend during hardware testing.
- [ ] Closing a handle and then issuing a transfer raises (test
      ``test_fake_handle_transfer_after_close_raises``).
- [ ] Viewer client ``shutdown()`` releases pending request waiters
      (test ``test_shutdown_unblocks_pending_transfers``).


Per-OS requirements
===================

- [ ] **Linux libusb**: udev rule documented for the target devices;
      tested without root.
- [ ] **Linux libusb**: ``libusb_detach_kernel_driver`` invoked before
      a HID device is claimed; reattached on close. Confirm host OS
      keyboard / mouse remains functional after a session.
- [ ] **Windows WinUSB** (Phase 2b — *not yet shipped*): the device
      must already be associated with WinUSB (Zadig / libwdi).
      Document the operator-facing instructions.
- [ ] **macOS IOKit** (Phase 2c — *not yet shipped*): notarisation
      story for non-App-Store distribution. Document SIP exclusions.
- [ ] All three backends: opening a device that another driver owns
      surfaces as a clear "busy" RuntimeError, not a hang or crash.


Pen-test scenarios
==================

These are recommended scenarios for an external pen-tester to attempt
*before* sign-off. None should succeed:

1. **ACL bypass via case folding**. Try VID/PID with mixed case and
   leading zeros; confirm only the canonical form matches.
2. **ACL bypass via Unicode normalization**. Try a serial string
   that is visually identical but Unicode-different from the rule.
3. **Credit DoS**. Send 1 million transfer frames as fast as
   possible against a small ``max_claims``; confirm host RSS stays
   bounded.
4. **Frame fragmentation attack**. Send a frame with a header that
   claims a payload size larger than what arrives; confirm
   ``decode_frame`` rejects the truncated stream.
5. **Concurrent OPEN race**. Two peers (or one peer with multiple
   threads) issuing OPEN simultaneously — confirm exactly one
   ``claim_id`` is granted per OPEN request and the bookkeeping
   doesn't drift.
6. **Audit tampering**. Edit an ``usb_*`` row in ``audit.db`` via
   raw SQLite; confirm ``verify_chain()`` flags the row.
7. **Prompt callback timing**. A slow prompt callback (sleeping 30s)
   should not allow another peer to slip a CTRL through in the
   meantime — confirm the prompt callback is awaited before any
   subsequent decision for the same vid/pid.
8. **Permission downgrade**. Run the host as a non-privileged user
   on Linux without the udev rule; confirm OPEN fails cleanly with
   a clear "permission denied" message rather than crashing.


Sign-off
========

Reviewer name: ____________________________________________________

Reviewer affiliation: _____________________________________________

Date: _____________________________________________________________

Items above all checked: [ ] yes  [ ] no — list failing items below.

Recommendation:

  [ ] Ready to ship Phase 2 default-on.
  [ ] Ready to ship behind opt-in flag (current state).
  [ ] Block release; remediation required.

Notes / remediation list:
