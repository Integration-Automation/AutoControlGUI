================================================
USB Passthrough — Phase 2 Design (DRAFT)
================================================

.. warning::
   **DRAFT — Linux-libusb path complete; cross-platform backends are
   structural skeletons only.**

   **Shipped (rounds 27 / 34 / 37 / 39 / 40 / 41 / 42):**
   Phase 1 (read-only enumeration), Phase 1.5 (hotplug events),
   Phase 2a (protocol + ABCs + ``LibusbBackend`` lifecycle +
   ``FakeUsbBackend`` for tests + feature flag, default off),
   Phase 2a.1 (full ``LibusbBackend`` transfers + CREDIT-based
   inbound flow control + audit hooks),
   **viewer-side ``UsbPassthroughClient``** (blocking
   open / control_transfer / bulk_transfer / interrupt_transfer / close
   with outbound credit waits and shutdown propagation),
   Phase 2d (``UsbAcl`` persistent allow-list, ACL-gated OPEN with
   prompt-callback path, audit-log integration via the existing
   tamper-evident chain).

   **Structural-only:** ``WinusbBackend`` (Phase 2b) and
   ``IokitBackend`` (Phase 2c) — class scaffolding + platform /
   dependency validation in place; ``list`` and ``open`` raise
   ``NotImplementedError`` referencing the in-module TODO list.
   These need ctypes / pyobjc wiring **plus hardware testing** to
   become real.

   **Process step:** Phase 2e — see
   :doc:`usb_passthrough_security_review` for the reviewer
   checklist that must be signed before the feature flag flips
   to default-on.

   Open questions stay flagged inline as ``OPEN`` for reviewers.

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
Bulk and interrupt USB transfers tolerate the latency far better
than they tolerate loss; the existing video/audio channels already
demonstrate that the underlying SCTP transport handles ordered
reliable streams adequately.

OPEN: Should we use ``maxPacketLifeTime`` instead, with a generous
budget (~5 s)? Worth measuring on real WAN links before shipping.

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

OPEN: Do we need fragmentation above 16 KiB? Most USB transfers fit;
control transfers are bounded by the device's wMaxPacketSize. A
follow-up frame with the same ``claim_id`` and a continuation flag
would be a low-cost addition.

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
``0xFF ERROR``    either                                     Protocol error / unsupported op
================  =========================================  ==============

OPEN: Should ``LIST`` go through the channel at all, or should the
viewer use the existing REST ``/usb/devices`` endpoint and only use
the channel for transfers? The latter is simpler but couples the
two transports.

Backpressure
------------

Each side starts with a credit window of 16 outstanding frames per
``claim_id``. Receiving a frame consumes one credit; a ``CREDIT``
message with a positive integer replenishes. Without flow control
a slow remote USB device would balloon DataChannel send buffers.

OPEN: Should credits be per-endpoint (IN/OUT separately) instead of
per-claim? Bulk endpoints are independent, so per-endpoint is more
faithful to the hardware. Costs more state.


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

OPEN: WinUSB requires the device to be *not already claimed* by another
driver. This rules out devices that the host OS thinks it owns
(printers, hubs, keyboards). We will need an in-app prompt explaining
why a particular device cannot be claimed.

macOS — IOKit
-------------

- ``IOUSBHostInterface`` (modern, since 10.12) or ``IOUSBInterfaceInterface``
  (older but ubiquitous) via ``pyobjc``.
- Requires entitlement signing if shipped through the App Store; for
  dev / direct distribution this is fine but the binary must be
  notarised.
- IOKit's ``CompletionMethod`` callbacks integrate with ``CFRunLoop``,
  not asyncio. We will need a thread that owns the runloop and
  marshals completions back to the WebRTC bridge thread.

OPEN: System Integrity Protection blocks claiming Apple devices and
some USB-C peripherals. Document the limit clearly.

Linux — libusb
--------------

- ``pyusb`` over ``libusb-1.0`` works without root if ``udev`` rules
  grant the user access; we will document a sample rule.
- Hot-detach handling: libusb fires ``LIBUSB_TRANSFER_NO_DEVICE``
  on in-flight transfers; we map that to ``CLOSED`` on the channel.

OPEN: Some distros default to attaching ``usbhid`` to anything that
looks like a HID. We must call ``libusb_detach_kernel_driver`` and,
on close, ``libusb_attach_kernel_driver`` to restore — otherwise the
host OS loses input devices.


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

OPEN: Should we sign or HMAC the ACL file so a compromised host
process cannot silently grant itself access? Probably yes, with a
master key derived from a user passphrase or platform keychain.

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
3. **Phase 2a (this design)**: protocol skeleton + ``UsbBackend`` ABC
   + Linux ``libusb`` backend behind a feature flag.
4. **Phase 2b**: Windows ``WinUSB`` backend.
5. **Phase 2c**: macOS ``IOKit`` backend.
6. **Phase 2d**: ACL persistence + host-side prompt UI + audit
   integration.
7. **Phase 2e**: external security review *before* default-on.

Each subphase is its own multi-round project. Estimated effort
(experienced contributor): ~1 week per backend, ~1 week for ACL/UI,
plus the security review which depends on a reviewer's calendar.


Open questions, summarised
==========================

1. ``maxRetransmits=None`` vs ``maxPacketLifeTime`` for the channel.
2. Frame fragmentation above 16 KiB.
3. ``LIST`` over the channel vs. exclusively over REST.
4. Backpressure granularity (per-claim vs per-endpoint).
5. What WinUSB cannot claim, and how to communicate that to the
   viewer.
6. macOS entitlement story for non-App-Store distribution.
7. Linux kernel-driver detach/reattach lifecycle.
8. ACL file integrity (HMAC vs platform keychain).
