===================================================
New Features (2026-06-19) — Unattended Reliability
===================================================

Three practitioner-pain fixes for unattended and login automation: mint
2FA codes, drive native file dialogs, and refuse to act on a locked
screen. Each ships through the full stack (facade, ``AC_*`` executor
commands, MCP tools, Script Builder) and is fully headless — external
steps are deterministic or injectable, so they unit-test without 2FA, a
real dialog, or a locked session.

.. contents::
   :local:
   :depth: 2


OTP / TOTP for 2FA logins
=========================

2FA blocks automated logins. Store the base32 secret (ideally in the
secrets store) and mint the current code mid-flow::

    from je_auto_control import generate_totp, verify_totp

    code = generate_totp(secret)          # 6-digit TOTP for "now"
    type_text(code)

``AC_otp_to_var`` writes the code into a flow variable for the next step::

    ["AC_otp_to_var", {"secret": "JBSWY3DPEHPK3PXP", "var": "otp"}]
    ["AC_type_keyboard", {"keycode": "${otp}"}]

Reuses the TOTP engine that backs remote-desktop auth. Executor command:
``AC_otp_to_var``; MCP tool: ``ac_generate_otp``.


Native file dialogs
===================

Recorders don't capture the OS file Open/Save/folder dialog, so everyone
hand-rolls "type the path + Enter". ``handle_file_dialog`` does it in one
call::

    from je_auto_control import handle_file_dialog

    handle_file_dialog("C:/reports/out.csv", action="save")

``action`` is ``open`` / ``save`` / ``folder`` (picking a default dialog
title) or pass an explicit ``window_title``; it waits for the dialog,
types the path, and presses ``confirm_key`` (default Enter). The
window-wait / type / confirm steps go through an injectable
:class:`FileDialogDriver`. Executor command: ``AC_handle_file_dialog``.


Locked-session guard
===================

Unattended runs silently fail when the workstation is locked or the RDP
session is disconnected — input no-ops or throws. Check first::

    from je_auto_control import ensure_interactive_session, is_session_locked

    ensure_interactive_session()          # raises if locked
    if is_session_locked():
        ...

On Windows the probe opens the input desktop (which fails when locked);
other platforms report "not locked" unless a custom probe is supplied.
Executor command: ``AC_assert_session_active`` — put it at the top of an
unattended script so it fails clearly instead of emitting phantom clicks.
