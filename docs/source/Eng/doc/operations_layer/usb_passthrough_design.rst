================================================
USB Passthrough — Phase 2 Design
================================================

.. note::
   **All software-side work is complete; the eight open questions are
   resolved (see "Design decisions").** Two items remain that cannot
   be completed in code: **verification against real USB hardware** and
   the **external human security sign-off (Phase 2e)**. The feature
   flag stays default-off until both are done.

   **Done and shipped (rounds 27 / 34 / 37 / 39 / 40 / 41 / 42 / 43):**
   Phase 1 (read-only enumeration), Phase 1.5 (hotplug events),
   Phase 2a (protocol + ABCs + ``LibusbBackend`` lifecycle +
   ``FakeUsbBackend`` for tests + feature flag, default off),
   Phase 2a.1 (full ``LibusbBackend`` transfers + CREDIT-based
   inbound flow control + audit hooks),
   **viewer-side ``UsbPassthroughClient``** (blocking
   open / control_transfer / bulk_transfer / interrupt_transfer / close /
   list_devices with outbound credit waits and shutdown propagation),
   Phase 2d (``UsbAcl`` persistent allow-list, ACL-gated OPEN with
   prompt-callback path, audit-log integration via the existing
   tamper-evident chain), Phase 2d.1 (ACL file HMAC-SHA256 integrity,
   fail-closed on tamper).

   **Phase 2b — Windows ``WinUSB``:** SetupAPI enumeration + ``WinUsb_*``
   transfer ctypes wiring complete (**hardware-unverified**).

   **Phase 2c — macOS ``IOKit``:** native IOKit enumeration via ctypes
   complete; device claim / transfers delegate to libusb (the
   hardware-proven path on macOS). See the ``iokit_backend`` module
   docstring (**hardware-unverified**).

   **Backend selection:** ``default_passthrough_backend()`` picks
   WinUSB / IOKit / libusb by OS automatically.

   **Remaining process step:** Phase 2e — see
   :doc:`usb_passthrough_security_review` for the reviewer checklist
   that must be signed by an external reviewer before the feature flag
   flips to default-on, plus the per-backend hardware test matrix.

.. contents::
   :local:
   :depth: 2


Goals
=====

Allow a remote AutoControl viewer to use a USB device that is
physically attached to the host. Concrete user stories:

- Plug a USB security key into the host machine; have it sign a
  WebAuthn challenge initiated by the viewer.
- Plug a USB-serial debug board into a lab host; let a remote
  developer talk to it via their local terminal.
- Plug a printer into the host; let the viewer's OS see the printer
  as if it were locally attached.

Non-Goals
=========

- **High-throughput isochronous transfers** (USB webcams, audio
  interfaces). The latency budget across WebRTC + DataChannel +
  driver round-trips is not compatible with isochronous USB. Use the
  existing audio/video tracks for those.
- **Automatic kernel-level device redirection** like USB/IP. We are
  building a userspace forwarder, not replacing a kernel driver.
- **Phase 2 will not ship without an explicit security review.**


Transport
=========

Channel
-------

A dedicated WebRTC ``DataChannel`` named ``usb`` per session, with
``ordered=True`` and ``maxRetransmits=None`` (full reliability).

**Wired up:** the host (``webrtc_host``) creates the ``usb`` channel and
feeds it to a session through ``UsbChannelHost`` (gated on viewer
authentication + the feature flag); the viewer (``webrtc_viewer``)
wraps the incoming channel in ``UsbChannelClient``, exposed via
``viewer.usb_client()`` for ``list_devices`` / ``open`` / ``resume``.
The adapters are transport-decoupled and unit-tested with a fake
channel (see ``test_usb_webrtc_channel``). **Reconnect:** OPENED carries
a ``resume_token``; if the host session outlives the viewer's transport
drop, the viewer sends ``RESUME{resume_token}`` to re-bind the existing
claim — keeping device state and ``claim_id`` — instead of re-OPENing.
Bulk and interrupt USB transfers tolerate the latency far better
than they tolerate loss; the existing video/audio channels already
demonstrate that the underlying SCTP transport handles ordered
reliable streams adequately.

**Resolved (OQ1):** keep ``ordered=True`` + ``maxRetransmits=None``
(fully reliable, ordered). USB control transfers (WebAuthn signing,
descriptor reads) have zero tolerance for loss — a partially-lost
stream corrupts the device state machine — so reliable-ordered
semantics matter more than shaving a few ms of retransmit latency.
The bounded-loss ``maxPacketLifeTime`` model is left for a future
loss-tolerant high-throughput use case (YAGNI today).

Framing
-------

Each channel message is one length-prefixed protocol frame::

    +----+--------+----------+--------------------+
    | 1B |   1B   |    2B    |       payload      |
    | op | flags  | claim_id | (op-specific body) |
    +----+--------+----------+--------------------+

- ``op``: 1-byte opcode (see *Operations* below)
- ``flags``: 8 bits, currently only ``EOF`` (bit 0) for chunked reads
- ``claim_id``: 16-bit identifier for one open device claim within
  the session. Allocated by the host at OPEN time, recycled at CLOSE.
- payload: opcode-specific. Bounded to 16 KiB to keep DataChannel
  message sizes reasonable.

**Resolved (OQ2):** fragmentation implemented.
``protocol.fragment_payload()`` splits a payload larger than 16 KiB
into multiple same-``claim_id`` frames, clearing ``FLAG_EOF`` on all
but the last; the receiver concatenates consecutive frame payloads
until it sees EOF. Both transfer replies and ``LIST`` replies use this
path; the common single-frame case still sends exactly one EOF-flagged
frame, so existing behaviour is unchanged.

Operations
----------

================  =========================================  ==============
Op (hex)          Direction                                  Purpose
================  =========================================  ==============
``0x01 LIST``     viewer → host, host → viewer (response)    Enumerate devices the viewer is permitted to claim
``0x02 OPEN``     viewer → host                              Request claim of (vendor_id, product_id, serial)
``0x03 OPENED``   host → viewer                              Reply: success + claim_id, or error
``0x04 CTRL``     viewer ↔ host                              Control transfer (bmRequestType, bRequest, wValue, wIndex, data)
``0x05 BULK``     viewer ↔ host                              Bulk IN/OUT transfer on a specific endpoint
``0x06 INT``      viewer ↔ host                              Interrupt IN/OUT transfer
``0x07 CREDIT``   viewer ↔ host                              Backpressure window update
``0x08 CLOSE``    viewer → host                              Release the claim
``0x09 CLOSED``   host → viewer                              Acknowledgement (or unsolicited on host-side disconnect)
``0x0A RESUME``   viewer → host                              Re-bind an existing claim after reconnect via resume_token
``0xFF ERROR``    either                                     Protocol error / unsupported op
================  =========================================  ==============

**Resolved (OQ3):** ``LIST`` goes over the channel. The session
handles a ``LIST`` frame and returns the devices the ACL would not
deny (a denied device is never even revealed to the viewer); the
viewer calls ``UsbPassthroughClient.list_devices()``. Enumeration and
transfers share one already-authenticated channel instead of coupling
in a second REST transport, and ACL filtering reuses the same logic as
the claim decision.

Backpressure
------------

Each side starts with a credit window of 16 outstanding frames per
``claim_id``. Receiving a frame consumes one credit; a ``CREDIT``
message with a positive integer replenishes. Without flow control
a slow remote USB device would balloon DataChannel send buffers.

**Resolved (OQ4):** keep per-claim credits. They already meet the core
goal — stopping a slow remote device from ballooning the host send
buffer — with the least state and the simplest reasoning.
Per-endpoint credits would track IN/OUT and each bulk endpoint
separately for a meaningful complexity jump that only matters when
multiple endpoints on one claim saturate at once; that is YAGNI until
real measurement shows head-of-line blocking.


Per-OS driver wrappers
======================

The driver layer is hidden behind a single ``UsbBackend`` ABC::

    class UsbBackend(abc.ABC):
        def open(self, vendor_id, product_id, serial) -> "UsbHandle": ...
        def list(self) -> list[UsbDevice]: ...

    class UsbHandle(abc.ABC):
        def control_transfer(self, ...): ...
        def bulk_transfer(self, endpoint, data, timeout_ms): ...
        def interrupt_transfer(self, endpoint, data, timeout_ms): ...
        def close(self): ...

This isolates the OS-specific bits and lets us write the protocol /
session layer without committing to a backend choice up front.

Windows — WinUSB
----------------

- Best path for HID-class devices we don't already own a driver for:
  install ``WinUSB`` via libwdi or have the user manually associate
  the device with WinUSB through Zadig.
- Use ``CreateFile`` + ``WinUsb_Initialize`` + ``WinUsb_ControlTransfer``
  / ``WinUsb_ReadPipe`` / ``WinUsb_WritePipe``.
- ``ctypes`` wrappers around ``winusb.dll`` are public API; no kernel
  driver authoring required.

**Resolved (OQ5):** WinUSB requires the device to be *not already
claimed* by another driver, and only devices already bound to
``winusb.sys`` appear in ``WinusbBackend.list()``. Devices the host OS
owns (printers, hubs, keyboards) therefore never list — the viewer
only ever sees the claimable subset and cannot mistake a system device
for one it could claim. An OPEN for a vid/pid not in the list returns a
clear ``no device matches`` error; the operator guide explains binding
a device to WinUSB via Zadig / libwdi.

macOS — IOKit
-------------

- Enumeration uses native IOKit through ``ctypes`` (no ``pyobjc``
  dependency): ``IOServiceGetMatchingServices`` over ``IOUSBDevice``
  plus ``IORegistryEntryCreateCFProperty`` reads of idVendor / idProduct
  / serial / locationID.
- Claim and transfers delegate to libusb (see OQ6) rather than
  hand-rolling the COM-style ``IOUSBHostInterface`` plugin vtable.

**Resolved (OQ6):** enumeration is native IOKit; claim / transfers
delegate to libusb — the hardware-proven USB path on macOS — which
avoids hand-coding an ``IOUSBHostInterface`` plugin vtable that could
not be verified without hardware. A directly distributed (non
App Store) build must be notarised; libusb device access needs no
special entitlement, but System Integrity Protection still hides Apple
internal devices and some USB-C peripherals. The operator guide
documents the SIP exclusion boundary.

Linux — libusb
--------------

- ``pyusb`` over ``libusb-1.0`` works without root if ``udev`` rules
  grant the user access; we will document a sample rule.
- Hot-detach handling: libusb fires ``LIBUSB_TRANSFER_NO_DEVICE``
  on in-flight transfers; we map that to ``CLOSED`` on the channel.

**Resolved (OQ7):** implemented. ``_LibusbHandle`` calls
``detach_kernel_driver`` for each interface of the active configuration
that the kernel actually holds on open, remembers which it touched, and
``attach_kernel_driver`` restores them on close — otherwise the host OS
permanently loses its keyboard / mouse after the session. libusb on
Windows / macOS raises ``NotImplementedError`` for detach, which is
tolerated and skipped (those platforms arbitrate drivers in the OS).


Security & ACL
==============

Per-device allow-list
---------------------

Stored in ``~/.je_auto_control/usb_acl.json``::

    {
      "version": 1,
      "rules": [
        {"vendor_id": "1050", "product_id": "0407", "label": "YubiKey 5",
         "allow": true, "prompt_on_open": true},
        ...
      ],
      "default": "deny"
    }

- Default policy is **deny**. A device the user has not explicitly
  allowed cannot be claimed.
- ``prompt_on_open`` triggers a host-side modal each time a viewer
  requests OPEN. The modal shows the vendor/product/serial and the
  viewer ID requesting access.
- Allow rules can be persisted with a "remember" checkbox in the
  prompt.

**Resolved (OQ8):** HMAC-SHA256 implemented. The ACL carries a sidecar
``<acl>.sig`` signature, verified on load; a mismatch fails closed
(default-deny, ``integrity_ok`` False) so a process that silently
rewrites the JSON cannot grant itself access without also forging the
signature. The signing key is pluggable — a deployment can pass a
keychain-derived key via the constructor's ``hmac_key=``; absent that,
a random key file is generated next to the ACL (``0o600`` on POSIX).
Note: a same-user process can still read the key file and forge a
signature, so keychain-derived keys are recommended for high-assurance
deployments (see operator guide). Files written before signing existed
are treated as legacy (still load, signed on next save); pass
``require_signature=True`` to reject unsigned files.

Audit
-----

Every OPEN, OPENED, CLOSE, and ERROR is appended to the existing
audit log under event_type ``"usb_passthrough"``. Frame-level
transfer logging is too noisy and is logged only on ERROR.

Privilege
---------

The host process must run with whatever privilege the chosen
backend requires (Linux udev rules, macOS entitlements, Windows
maybe nothing for WinUSB). The README will spell this out per-OS.


Phasing
=======

1. **Done — Phase 1**: read-only enumeration (``list_usb_devices``).
2. **Done — Phase 1.5**: hotplug events (``UsbHotplugWatcher``,
   ``/usb/events``).
3. **Done — Phase 2a**: protocol + ``UsbBackend`` ABC + Linux
   ``libusb`` backend behind a feature flag.
4. **Done — Phase 2b**: Windows ``WinUSB`` backend (ctypes,
   hardware-unverified).
5. **Done — Phase 2c**: macOS ``IOKit`` backend (native enumeration +
   libusb transfers, hardware-unverified).
6. **Done — Phase 2d / 2d.1**: ACL persistence + host-side prompt
   callback + audit integration + ACL file HMAC integrity.
7. **In progress — Phase 2e**: external security review *before*
   default-on, **plus** the per-backend real-hardware test matrix.
   Both inherently require hardware and an external reviewer and cannot
   be completed in code alone.

The feature flag stays default-off until Phase 2e is signed off.


Design decisions (formerly open questions)
==========================================

All eight original open questions are resolved; see the matching
sections above for the implementation.

1. **OQ1 — channel reliability**: ``maxRetransmits=None`` (fully
   reliable, ordered).
2. **OQ2 — frame fragmentation**: implemented via ``fragment_payload``
   + EOF reassembly.
3. **OQ3 — ``LIST`` over the channel**: yes, ACL-filtered, over the
   channel.
4. **OQ4 — backpressure granularity**: per-claim (per-endpoint is
   YAGNI).
5. **OQ5 — what WinUSB cannot claim**: only WinUSB-bound devices list;
   a failed claim returns a clear error.
6. **OQ6 — macOS distribution**: native IOKit enumeration + libusb
   transfers; notarisation, no special entitlement, SIP boundary
   documented.
7. **OQ7 — Linux kernel driver**: detach on open, reattach on close.
8. **OQ8 — ACL integrity**: HMAC-SHA256 sidecar, pluggable
   (keychain-capable) key.
