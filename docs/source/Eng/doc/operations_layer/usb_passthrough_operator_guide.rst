============================================================
USB Passthrough — Operator Guide
============================================================

Step-by-step recipe for getting a USB device on a host machine to
respond to traffic from a remote viewer. Host-side end-to-end works on
Linux libusb; Windows WinUSB and macOS IOKit are implemented but
**hardware-unverified** — both must pass the Phase 2e hardware test
matrix before production use. ``default_passthrough_backend()`` picks
the right backend for the current OS.

If you're a security reviewer instead of an operator, you want
:doc:`usb_passthrough_security_review`. If you're a developer wanting
the protocol details, :doc:`usb_passthrough_design`.

.. contents::
   :local:
   :depth: 2


Prerequisites
=============

On the **host** (the machine with the physical USB device):

- Python 3.10+ with AutoControl installed.
- The optional ``webrtc`` extra: ``pip install je_auto_control[webrtc]``.
- ``pyusb`` installed if you want the libusb backend:
  ``pip install pyusb``.
- The USB device the viewer will use, plugged in.
- Per-OS setup (see *Driver setup* below).

On the **viewer** (the remote machine that will use the device):

- Python 3.10+ with AutoControl installed.
- Network reach to the host's REST API port (default 9939) **and** to
  the WebRTC signalling / TURN endpoints if the viewer is behind NAT.
- The host's bearer token (operator hands it over out-of-band).


Driver setup (per OS)
=====================

Linux (libusb)
--------------

The libusb backend is the most-tested path today. Steps:

1. Install ``libusb-1.0`` development files (e.g. ``apt install
   libusb-1.0-0``).
2. Add a ``udev`` rule so the AutoControl host process can claim the
   device without root. Example for a YubiKey 5
   (vendor ``1050``, product ``0407``)::

       # /etc/udev/rules.d/99-autocontrol-usb.rules
       SUBSYSTEM=="usb", ATTRS{idVendor}=="1050",
         ATTRS{idProduct}=="0407", MODE="0660",
         GROUP="plugdev"

   Then ``sudo udevadm control --reload && sudo udevadm trigger``.
3. Make sure your AutoControl user is in ``plugdev``.
4. If the device is a HID, AutoControl's libusb wrapper detaches
   ``usbhid`` on ``open`` and re-attaches on ``close``. Don't be
   alarmed if your local keyboard input briefly hiccups during a
   claim of a HID device.

Windows (WinUSB) — *hardware-unverified*
----------------------------------------

The ctypes wiring exists but has not been validated against real
hardware. Treat as alpha. Steps:

1. Use `Zadig <https://zadig.akeo.ie/>`_ or libwdi to associate the
   target device with the WinUSB driver. Do not do this for devices
   the host OS already manages (printers, hubs, keyboards).
2. After binding, the device should appear in
   ``WinusbBackend().list()``.
3. Hardware testing is required before relying on transfers. See
   the security review checklist for the expected test matrix.

macOS (IOKit) — *hardware-unverified*
-------------------------------------

``IokitBackend`` enumerates USB devices natively through IOKit
(``ctypes``; no pyobjc needed), so ``IokitBackend().list()`` works.
Claiming a device for transfers delegates to libusb, so install it:
``pip install pyusb`` and ``brew install libusb``. Notes:

1. A directly distributed (non App Store) build must be notarised.
   libusb device access needs no special entitlement.
2. System Integrity Protection hides Apple internal devices and some
   USB-C peripherals — they will not appear in ``list()`` and cannot be
   claimed. This is expected.
3. Transfers are hardware-unverified; see the security review checklist
   for the expected test matrix before relying on them.


Enabling the feature
====================

USB passthrough is **off by default**. Two ways to opt in:

- Environment variable, picked up at process start::

      export JE_AUTOCONTROL_USB_PASSTHROUGH=1
      python -m je_auto_control.cli start-rest

- Programmatic, in your bootstrap script (overrides env)::

      from je_auto_control.utils.usb.passthrough import enable_usb_passthrough
      enable_usb_passthrough(True)

Confirm with :func:`is_usb_passthrough_enabled`::

      from je_auto_control.utils.usb.passthrough import is_usb_passthrough_enabled
      assert is_usb_passthrough_enabled()


ACL setup
=========

The ACL defaults to ``"deny"`` so a viewer cannot claim a device the
operator hasn't approved. Add per-device rules:

1. From the GUI — the *USB* tab on the host shows the prompt dialog
   on first OPEN of an unknown device. Tick *Remember this decision*
   to persist a permanent allow rule.
2. From Python::

      from je_auto_control.utils.usb.passthrough import (
          AclRule, UsbAcl,
      )
      acl = UsbAcl()
      acl.add_rule(AclRule(
          vendor_id="1050", product_id="0407",
          serial=None,            # match any serial
          label="YubiKey 5",
          allow=True,
          prompt_on_open=False,   # silent allow once approved
      ))

3. By editing ``~/.je_auto_control/usb_acl.json`` directly. The file
   is permission-checked (mode ``0600`` on POSIX). Bad JSON or an
   unknown ``version`` falls back to default-deny. **If you hand-edit
   the file, the HMAC signature will no longer match and the ACL fails
   closed** (see below) — re-save through ``UsbAcl`` instead, which
   refreshes the signature.

Decision precedence:

- First matching rule wins. ``prompt_on_open=True`` means re-ask the
  operator each time, even if the rule is ``allow=True``.
- If no rule matches, the file's ``default`` (``"deny"`` out of the
  box) applies.

ACL file integrity (HMAC)
-------------------------

The ACL is protected by an HMAC-SHA256 signature stored in a sidecar
``usb_acl.json.sig``. On load the signature is verified against the
file bytes; a mismatch makes the ACL **fail closed** (default-deny,
``UsbAcl.integrity_ok`` reports ``False``). This stops a process that
silently rewrites the JSON from granting itself access.

- By default the signing key is a random 32-byte file
  ``usb_acl.json.key`` (mode ``0600`` on POSIX), created on first save.
- For higher assurance, derive the key from a platform keychain and
  pass it explicitly: ``UsbAcl(hmac_key=<bytes>)``. A same-user process
  that can read the key file could otherwise forge a signature.
- Pass ``UsbAcl(require_signature=True)`` to reject even legacy
  unsigned files outright.


Starting the host
=================

The host needs the REST API running (so the viewer can enumerate)
and a WebRTC peer connection to the viewer (so transfers can flow).

REST::

    from je_auto_control.utils.rest_api import start_rest_api_server
    server = start_rest_api_server(host="0.0.0.0", port=9939)
    print("Bearer:", server.token)

WebRTC: use the existing remote desktop pipeline (see
:doc:`operations_layer_doc`) to bring up a session. The viewer's
``UsbPassthroughClient`` then plugs into the negotiated DataChannel.


Viewer-side: claim and transfer
===============================

Enumerate
---------

From Python::

    import urllib.request, json
    req = urllib.request.Request(
        "http://host:9939/usb/devices",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.loads(r.read())
    for d in body["devices"]:
        print(d["vendor_id"], d["product_id"], d.get("product"))

Or via the *USB Browser* GUI tab on the viewer side: paste the host's
REST URL + token, click *Fetch devices*.

Open + transfer
---------------

::

    from je_auto_control.utils.usb.passthrough import (
        UsbPassthroughClient, encode_frame, decode_frame,
    )

    # `data_channel` is your WebRTC RTCDataChannel for the "usb" channel.
    def send(frame):
        data_channel.send(encode_frame(frame))

    client = UsbPassthroughClient(send_frame=send)
    # Wire the channel's on-message callback:
    data_channel.on("message")(lambda raw: client.feed_frame(decode_frame(raw)))

    handle = client.open(vendor_id="1050", product_id="0407")
    response = handle.control_transfer(
        bm_request_type=0xC0, b_request=6, w_value=0x0100, length=18,
    )
    print("device descriptor:", response.hex())
    handle.close()
    client.shutdown()

Errors:

- ``UsbClientTimeout`` — the host took longer than ``reply_timeout_s``
  (default 10s) to respond. Check the network / host process.
- ``UsbClientError`` — the host replied with ``{ok: false, error: ...}``.
  The most common case is *denied by ACL policy* — go check the
  prompt dialog or the ACL rule on the host.
- ``UsbClientClosed`` — the client or its handle was already shut down.


Troubleshooting matrix
======================

==========================================  =====================================================
Symptom                                     Likely cause / fix
==========================================  =====================================================
``open`` returns ``denied by ACL policy``   No allow rule + ``default = deny``. Add a rule or
                                            enable a prompt callback.
``open`` returns ``no device matches``      Device not enumerated. Check ``UsbHotplugWatcher``
                                            output or run ``list_usb_devices()`` directly.
                                            On Windows, confirm Zadig binding.
``credit exhausted`` on transfer            Viewer sent more frames than the host's
                                            ``initial_credits`` window allows. Either lower
                                            request rate or raise ``initial_credits`` on
                                            the session.
Transfer ``UsbClientTimeout``               Host process is busy or the WebRTC channel is
                                            broken. Inspect the *Packet Inspector* tab for
                                            RTT / packet loss.
After OPEN, host's keyboard stops working   Linux: a HID device was claimed and
                                            ``usbhid`` was detached. The driver re-attaches
                                            on CLOSE; if not, ``udevadm trigger`` to recover.
Audit chain shows ``broken_at_id``          Someone edited ``audit.db`` directly. Restore
                                            from a backup; investigate.
==========================================  =====================================================


What is *not* shipped yet
=========================

- The *USB Sharing* tab is the simple, AnyDesk-style surface: enable
  sharing on the left and Allow / Block local devices in the ACL; on the
  right, list the shared devices over the in-process channel and *Open*
  one (a descriptor read proves the full stack). The *USB Browser* tab's
  *Open* button now also works against a **localhost** target via the
  same loopback path.
- Cross-machine is fully wired: the WebRTC host creates a ``usb``
  DataChannel and the viewer exposes ``viewer.usb_client()`` (a
  ``UsbChannelClient`` with ``list_devices`` / ``open`` / ``resume``).
  The *USB Sharing* panel has a **Source** selector — pick *Remote
  (WebRTC)* and the List / Open buttons run against the live WebRTC
  viewer's host (via ``registry.webrtc_usb_client()``); pick *Local
  (loopback)* for same-machine use. You can also drive it from Python.
- Windows WinUSB and macOS IOKit transfer paths are written but not yet
  validated against real hardware. Do not use in production until the
  Phase 2e hardware test matrix passes.
- Phase 2e external security review has not been signed; the feature
  flag must remain explicit opt-in.
