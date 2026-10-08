# Wayland authorisation — manual checklist (GNOME and KDE)

**Status: NOT EXECUTED.** Nobody has run these steps. They were written on a
Windows machine, against the code and against fakes, and exist because the
things they check have no CI job: a real consent dialog, a real person
answering it, and a real GlobalShortcuts portal. Do not cite this file as
evidence that any of it works. When someone runs it, record the desktop,
versions, date and result in `docs/updates/` and change this line.

What CI already covers, so it is not repeated here: the portal handshake
against a real `liboeffis` and a scripted portal (`portal-verification`), the
libei sender against a real `libeis` (`eis-verification`), capture against
headless sway (`wayland-verification`).

## Before you start

- A Wayland session: GNOME 45+ (mutter) for sections A–D, KDE Plasma 6 for a
  second pass. Record `echo $XDG_SESSION_TYPE $XDG_CURRENT_DESKTOP` and the
  versions of `libei`, `liboeffis`, `xdg-desktop-portal` and its backend.
- `libei` and `liboeffis` installed (`python -c "from je_auto_control.linux_wayland import oeffis; print(oeffis.is_available())"` prints `True`).
- `ydotool` 1.0+ installed **and `ydotoold` running** — the point of several
  steps is that it is available and must still not be used.
- `JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND` unset.
- A text editor focused, so a stray keystroke is visible.
- In every step, "probe" means:

  ```bash
  python -c "import json, je_auto_control as ac; print(json.dumps(ac.probe_capabilities().to_dict()['capabilities'][0], indent=1))"
  ```

## A. Probing asks for nothing

- [ ] A1. Fresh terminal. Run the probe. **Expect:** no dialog appears, no
      key is typed; `state` is `not_requested`, `backend` is `libei`,
      `restore_token` is `unsupported`.
- [ ] A2. Open the GUI, Diagnostics tab. **Expect:** no dialog; the second
      table shows four rows; the input row reads "Not asked yet".

## B. Allow

- [ ] B1. `python -c "import je_auto_control as ac; ac.type_keyboard('a')"`.
      **Expect:** the desktop's remote-control dialog appears.
- [ ] B2. While the dialog is up, run the probe in a second terminal.
      **Expect:** `state` is `not_requested` there (the ledger is per
      process) — note this; the `requesting` state is only visible from
      inside the asking process, e.g. the GUI's Diagnostics tab.
- [ ] B3. Click **Share / Allow**. **Expect:** one `a` is typed, exactly once.
- [ ] B4. In one Python session: type a key (allow), then
      `ac.probe_capabilities().input.state`. **Expect:** `available`.

## C. Deny — the step this change exists for

- [ ] C1. New Python session:
      `import je_auto_control as ac; ac.type_keyboard('a')`, and **dismiss /
      deny** the dialog.
      **Expect:** `WaylandAuthorisationError` is raised; **no `a` is typed**
      (ydotoold is running and must not have been used).
- [ ] C2. Read the message. **Expect:** it names
      `reset_input_authorisation()` and `JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli`.
- [ ] C3. `ac.probe_capabilities().input` — **Expect:** `state` is
      `needs_permission`, `authorisation` is `declined`.
      **If instead an `a` was typed and `authorisation` is `failed`:** this
      desktop's liboeffis words the refusal without "denied". Record
      `ac.probe_capabilities().input.detail` verbatim — that string is what
      `PortalConsentNotGranted.declined` in `linux_wayland/oeffis.py` has to
      recognise — and file it. This is the single most useful result this
      checklist can produce.
- [ ] C4. `ac.type_keyboard('a')` again. **Expect:** raises again, and **no
      second dialog** appears.
- [ ] C5. `ac.reset_input_authorisation(); ac.type_keyboard('a')`.
      **Expect:** the dialog appears again; allowing it types one `a`.

## D. Leave the dialog open, revoke, restart

- [ ] D1. New session, `ac.type_keyboard('a')`, and do **not** answer for 35
      seconds. **Expect:** the call returns or raises on its own after ~30 s
      (it must not hang). Record which, whether an `a` was typed through
      ydotool, and the probe's `state` (`needs_permission`, authorisation
      `timed_out`). Note whether the dialog is still on screen afterwards.
- [ ] D2. After an allowed session (B4), revoke it from the desktop: on GNOME
      click the screen-sharing indicator in the top bar and stop sharing; on
      KDE use the system-tray remote-control item. Then `ac.type_keyboard('a')`.
      **Expect:** `WaylandAuthorisationError`, no `a` typed, probe `state` is
      `revoked`. Record whether the desktop actually offers a way to revoke.
- [ ] D3. After an allowed session, `ac.close_input_session()`.
      **Expect:** the sharing indicator disappears; probe `state` is
      `session_closed`; the next `ac.type_keyboard('a')` asks again.
- [ ] D4. (GNOME on Wayland cannot restart mutter without ending the session;
      do this on KDE with `kwin_wayland --replace &`, or on sway.) After an
      allowed session, restart the compositor, then probe from the *same*
      Python session. **Expect:** `compositor_restarted`. Record what
      actually happens — the Python session may not survive.

## E. Explicit ydotool, and XWayland

- [ ] E1. `JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli python -c "import je_auto_control as ac; ac.type_keyboard('a')"`.
      **Expect:** no dialog at all, one `a` typed; probe `backend` is `ydotool`.
- [ ] E2. `JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11` and run the probe.
      **Expect:** `xwayland` is true in the snapshot; every capability has
      `desktop_wide: false`; the Diagnostics tab's "Reaches" column reads
      "X11 applications only (XWayland)".
- [ ] E3. Still under E2, focus a native Wayland window (GNOME Text Editor)
      and type a key through AutoControl. **Expect:** nothing arrives. Focus
      an XWayland window (`xterm`) and repeat. **Expect:** it arrives. This
      confirms the stated scope is the real one.

## F. Screenshot portal

- [ ] F1. With no `grim`, `gnome-screenshot` or `spectacle` on `PATH`, take a
      screenshot and **deny** the dialog. **Expect:** a capture error naming
      the dismissal; probe capture `state` is `needs_permission`.
- [ ] F2. Repeat and **allow**. **Expect:** an image; `state` is `available`.

## G. Recording your own input

- [ ] G1. `python -c "import je_auto_control as ac; [print(d) for d in ac.list_input_devices()]"`.
      **Expect:** your keyboard has `is_virtual` false; with `ydotoold`
      running, its device is listed with `is_virtual` true (check
      `d.sysfs` contains `/devices/virtual/input/`). **If a Bluetooth
      keyboard is connected, expect `is_virtual` false for it** — record its
      `sysfs` path either way.
- [ ] G2. As a user **not** in the `input` group, start a `PhysicalRecorder`
      on your keyboard. **Expect:** `InputPermissionError` whose text names
      the `input` group and says not to run as root.
- [ ] G3. As a user in the `input` group: start on `[keyboard, ydotoold]`,
      type `abc` by hand, run `ydotool type xyz`, stop. **Expect:** the events
      contain your `abc` key codes and **none** of `xyz`;
      `recorder.excluded` lists the ydotoold device.

## H. Global stop shortcut

Not covered by any CI job; the fake in the unit tests is the only thing this
has ever talked to.

- [ ] H1. ```python
      import threading, je_auto_control as ac
      stop = threading.Event()
      s = ac.StopShortcutSession(stop.set, preferred_trigger="CTRL+ALT+F12")
      s.open(); s.start()
      ```
      **Expect:** either the desktop shows a dialog to confirm / assign the
      shortcut, or — where the desktop's portal has no GlobalShortcuts
      interface — `ShortcutUnavailable` naming the GUI stop control. Which
      desktops and versions implement it was not established when this was
      written; record the desktop, its version, which of the two happened,
      and the exact message.
- [ ] H2. Allow it, press the shortcut. **Expect:** `stop.is_set()` is true.
- [ ] H3. Press other keys. **Expect:** nothing is reported for them.
- [ ] H4. `s.close()`, press the shortcut. **Expect:** nothing; the shortcut
      no longer appears in the desktop's shortcut settings for this app.
- [ ] H5. Repeat H1 and **deny**. **Expect:** `ShortcutPermissionError`
      whose `recovery` names the stop methods that still work; nothing is
      left registered.

## I. The helper process (opt-in)

- [ ] I1. `JE_AUTOCONTROL_WAYLAND_EI_WORKER=1`, then B1–B3. **Expect:** the
      same single dialog and the same single `a`; `pgrep -f ei_worker` shows
      one helper.
- [ ] I2. Hold a key through the helper
      (`ac.press_keyboard_key('shift')`), then `kill -9` the helper.
      **Expect:** the key does not stay stuck on the desktop (type a letter —
      it should be lower-case). The next action raises `EiWorkerDied` listing
      the key. Record whether the key was stuck: releasing it is the
      compositor's job, and this is the only place that is checked on a real
      one.
- [ ] I3. Exit Python normally with the helper running. **Expect:**
      `pgrep -f ei_worker` shows nothing.
